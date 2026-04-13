"""Naukri bot."""

import asyncio
from urllib.parse import quote_plus

from playwright.async_api import Page

from utils.browser_utils import capture_failure, first_visible, safe_click, safe_fill, safe_goto
from utils.form_autofill import autofill_application_questions, build_application_profile
from utils.tracker import is_duplicate_application, log_application


class NaukriBot:
    def __init__(self, config: dict):
        self.email = config["platforms"]["naukri"]["email"]
        self.password = config["platforms"]["naukri"]["password"]
        self.job_titles = config["job_titles"]
        self.locations = config["locations"]
        self.delay = config["delay_between_actions"]
        self.max_apps = config["max_applications_per_day"]
        self.applied_count = 0
        self.base_url = "https://www.naukri.com"
        self.platform_name = "Naukri"
        self.dry_run = bool(config.get("dry_run", False))
        self.application_profile = build_application_profile(config)

    async def login(self, page: Page):
        print("Naukri login started")
        try:
            await safe_goto(page, f"{self.base_url}/nlogin/login")
            await asyncio.sleep(self.delay)

            email_ok = await safe_fill(
                page,
                [
                    "input[placeholder='Enter your active Email ID / Username']",
                    "input[type='email']",
                    "input[type='text']",
                ],
                self.email,
            )
            password_ok = await safe_fill(
                page,
                ["input[placeholder='Enter your password']", "input[type='password']"],
                self.password,
            )
            submit_ok = await safe_click(page, ["button[type='submit']"])

            if not (email_ok and password_ok and submit_ok):
                print("Naukri login form elements not found")
                return False

            await asyncio.sleep(4)
            if "login" not in page.url:
                print("Naukri login successful")
                return True

            print("Naukri login failed")
            return False
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "login", exc)
            print(f"Naukri login failed with error: {exc}")
            return False

    async def search_jobs(self, page: Page, job_title: str, location: str):
        print(f"Naukri search: {job_title} in {location}")
        slug_title = quote_plus(job_title).replace("+", "-")
        slug_location = quote_plus(location).replace("+", "-")
        search_url = f"{self.base_url}/{slug_title}-jobs-in-{slug_location}"

        try:
            await safe_goto(page, search_url)
            await asyncio.sleep(self.delay)
            cards = await page.query_selector_all(".jobTuple")
            print(f"Naukri listings found: {len(cards)}")
            return cards
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "search_jobs", exc)
            print(f"Naukri search failed: {exc}")
            return []

    async def apply_to_job(self, page: Page, job_card):
        if self.applied_count >= self.max_apps:
            return False

        try:
            title_el = await first_visible(job_card, [".title", "a.title"])
            company_el = await first_visible(job_card, [".comp-name", ".companyInfo"])
            location_el = await first_visible(job_card, [".loc", ".location"])

            if not title_el:
                return False

            title = (await title_el.inner_text()).strip() if title_el else "Unknown"
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
            location = (await location_el.inner_text()).strip() if location_el else "Unknown"

            before_pages = list(page.context.pages)
            await title_el.click()
            await asyncio.sleep(self.delay)
            after_pages = list(page.context.pages)
            job_page = after_pages[-1] if len(after_pages) > len(before_pages) else page
            job_url = job_page.url

            if is_duplicate_application(self.platform_name, company, title, job_url):
                print(f"Skipped duplicate: {company} - {title}")
                if job_page != page:
                    await job_page.close()
                return False

            if self.dry_run:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location,
                    status="Dry Run",
                    job_url=job_url,
                )
                print(f"Dry run logged: {company} - {title}")
                if job_page != page:
                    await job_page.close()
                return True

            apply_btn = await first_visible(
                job_page,
                [
                    "button#apply-button",
                    "button.apply-button",
                    "button:has-text('Apply')",
                    "a:has-text('Apply')",
                ],
            )
            if not apply_btn:
                if job_page != page:
                    await job_page.close()
                return False

            await apply_btn.click()
            await asyncio.sleep(2)

            for _ in range(4):
                filled_count = await autofill_application_questions(job_page, self.application_profile)
                if filled_count:
                    print(f"Naukri autofilled {filled_count} fields")

                next_btn = await first_visible(
                    job_page,
                    [
                        "button:has-text('Continue')",
                        "button:has-text('Next')",
                        "button:has-text('Save & Continue')",
                    ],
                )
                if not next_btn:
                    break
                await next_btn.click()
                await asyncio.sleep(1)

            already_applied = await job_page.query_selector("text=already applied")
            if already_applied:
                status = "Already Applied"
            else:
                status = "Applied"
                self.applied_count += 1

            log_application(
                self.platform_name,
                company,
                title,
                location,
                status=status,
                job_url=job_url,
            )
            print(f"{self.platform_name} {status.lower()}: {company} - {title}")

            if job_page != page:
                await job_page.close()
            return True
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "apply_to_job", exc)
            print(f"Naukri apply error: {exc}")
            return False

    async def run(self, page: Page):
        print("Naukri bot starting")
        if not await self.login(page):
            return

        for job_title in self.job_titles:
            for location in self.locations:
                if self.applied_count >= self.max_apps:
                    break

                cards = await self.search_jobs(page, job_title, location)
                for card in cards[:5]:
                    if self.applied_count >= self.max_apps:
                        break
                    await self.apply_to_job(page, card)
                    await asyncio.sleep(self.delay)

        print(f"Naukri bot done. Applied: {self.applied_count}")
