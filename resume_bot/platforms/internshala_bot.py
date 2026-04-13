"""Internshala bot."""

import asyncio

from playwright.async_api import Page

from utils.browser_utils import capture_failure, first_visible, human_pause, safe_click, safe_fill, safe_goto
from utils.form_autofill import autofill_application_questions, build_application_profile
from utils.job_intelligence import extract_job_text, find_external_links, keyword_match
from utils.tracker import is_duplicate_application, log_application, log_external_link


class InternshalaBot:
    def __init__(self, config: dict):
        self.email = config["platforms"]["internshala"]["email"]
        self.password = config["platforms"]["internshala"]["password"]
        self.job_titles = config["job_titles"]
        self.delay = config["delay_between_actions"]
        self.delay_jitter_min = float(config.get("delay_jitter_min", 0.8))
        self.delay_jitter_max = float(config.get("delay_jitter_max", 2.0))
        self.max_apps = config["max_applications_per_day"]
        self.applied_count = 0
        self.base_url = "https://internshala.com"
        self.platform_name = "Internshala"
        self.dry_run = bool(config.get("dry_run", False))
        self.application_profile = build_application_profile(config)
        self.requirement_keywords = list(config.get("requirement_keywords", []))
        self.min_keyword_matches = int(config.get("min_keyword_matches", 1))
        self.platform_domains = ["internshala.com"]

    async def login(self, page: Page):
        print("Internshala login started")
        try:
            for attempt in range(1, 3):
                await safe_goto(page, f"{self.base_url}/login/student")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

                email_ok = await safe_fill(page, ["#modal_email", "input[type='email']"], self.email)
                password_ok = await safe_fill(page, ["#modal_password", "input[type='password']"], self.password)
                submit_ok = await safe_click(page, ["#modal_login_submit", "button[type='submit']"])

                if not (email_ok and password_ok and submit_ok):
                    print("Internshala login form elements not found")
                    return False

                await human_pause(self.delay + 1, self.delay_jitter_min, self.delay_jitter_max)
                profile_icon = await first_visible(page, ["#header_profile", "#user-menu-container"])
                if "login" not in page.url or profile_icon:
                    print("Internshala login successful")
                    return True
                print(f"Internshala login retry {attempt}/2")
            print("Internshala login failed")
            return False
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "login", exc)
            print(f"Internshala login error: {exc}")
            return False

    async def _extract_listing_urls(self, page: Page, search_url: str):
        await safe_goto(page, search_url)
        await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

        listings = await page.query_selector_all(".individual_internship")
        urls = []
        for listing in listings[:5]:
            link = await first_visible(listing, ["a.view_detail_button", "a"])
            if not link:
                continue
            href = await link.get_attribute("href")
            if not href:
                continue
            urls.append(f"{self.base_url}{href}" if href.startswith("/") else href)
        return urls

    async def search_internships(self, page: Page, keyword: str):
        print(f"Internshala internships search: {keyword}")
        search_url = f"{self.base_url}/internships/keywords-{keyword.lower().replace(' ', '-')}"
        try:
            urls = await self._extract_listing_urls(page, search_url)
            print(f"Internshala internships found: {len(urls)}")
            return urls
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "search_internships", exc)
            print(f"Internshala internships search failed: {exc}")
            return []

    async def search_jobs(self, page: Page, keyword: str):
        print(f"Internshala jobs search: {keyword}")
        search_url = f"{self.base_url}/jobs/keywords-{keyword.lower().replace(' ', '-')}"
        try:
            urls = await self._extract_listing_urls(page, search_url)
            print(f"Internshala jobs found: {len(urls)}")
            return urls
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "search_jobs", exc)
            print(f"Internshala jobs search failed: {exc}")
            return []

    async def apply_to_listing(self, page: Page, listing_url: str, listing_type: str):
        if self.applied_count >= self.max_apps:
            return False

        try:
            await safe_goto(page, listing_url)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

            title_el = await first_visible(page, [".profile", "h1"])
            company_el = await first_visible(page, [".company_name", ".company"])
            title = (await title_el.inner_text()).strip() if title_el else "Unknown Role"
            company = (await company_el.inner_text()).strip() if company_el else "Unknown Company"

            if is_duplicate_application(self.platform_name, company, title, listing_url):
                print(f"Skipped duplicate: {company} - {title}")
                return False

            job_text = await extract_job_text(page)
            is_match, matched_keywords = keyword_match(job_text, self.requirement_keywords, self.min_keyword_matches)
            if not is_match:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    "",
                    status="Skipped - Keyword Mismatch",
                    job_url=listing_url,
                    notes=listing_type,
                )
                print(f"Skipped keyword mismatch: {company} - {title}")
                return False

            external_links = await find_external_links(page, self.platform_domains)
            for external_url in external_links[:3]:
                log_external_link(
                    self.platform_name,
                    company,
                    title,
                    listing_url,
                    external_url,
                    notes=listing_type + " | Matched: " + ", ".join(matched_keywords[:8]),
                )

            if self.dry_run:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    "",
                    status="Dry Run",
                    job_url=listing_url,
                    notes=listing_type + " | Matched: " + ", ".join(matched_keywords[:8]),
                )
                print(f"Dry run logged: {company} - {title}")
                return True

            apply_btn = await first_visible(
                page,
                ["#easy_apply_button", ".btn-primary.apply_now_btn", "button:has-text('Apply')"],
            )
            if not apply_btn:
                return False

            btn_text = (await apply_btn.inner_text()).strip().lower()
            if "applied" in btn_text:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    "",
                    status="Already Applied",
                    job_url=listing_url,
                    notes=listing_type,
                )
                return False

            await apply_btn.click()
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

            filled_count = await autofill_application_questions(page, self.application_profile)
            if filled_count:
                print(f"Internshala autofilled {filled_count} fields")

            cover_letter = await first_visible(page, ["textarea.cover_letter_ta", "textarea[name='cover_letter']"])
            if cover_letter:
                default_cl = (
                    f"I am interested in this {listing_type} role at {company}. "
                    "My skills are aligned with the requirements."
                )
                await cover_letter.fill(default_cl)
                await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)

            submit_ok = await safe_click(page, ["button#submit", ".submit-btn", "button:has-text('Submit')"])
            if not submit_ok:
                return False

            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
            self.applied_count += 1
            log_application(
                self.platform_name,
                company,
                title,
                "",
                status="Applied",
                job_url=listing_url,
                notes=listing_type + " | Matched: " + ", ".join(matched_keywords[:8]),
            )
            print(f"Internshala applied: {company} - {title}")
            return True
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "apply_to_listing", exc)
            print(f"Internshala apply error: {exc}")
            return False

    async def run(self, page: Page):
        print("Internshala bot starting")
        if not await self.login(page):
            return

        for keyword in self.job_titles:
            if self.applied_count >= self.max_apps:
                break

            internship_urls = await self.search_internships(page, keyword)
            for listing_url in internship_urls:
                if self.applied_count >= self.max_apps:
                    break
                await self.apply_to_listing(page, listing_url, "internship")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

            job_urls = await self.search_jobs(page, keyword)
            for listing_url in job_urls:
                if self.applied_count >= self.max_apps:
                    break
                await self.apply_to_listing(page, listing_url, "job")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

        print(f"Internshala bot done. Applied: {self.applied_count}")
