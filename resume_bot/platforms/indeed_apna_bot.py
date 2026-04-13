"""Indeed and Apna bots."""

import asyncio

from playwright.async_api import Page

from utils.browser_utils import capture_failure, first_visible, human_pause, safe_click, safe_fill, safe_goto
from utils.external_apply import handle_external_link
from utils.form_autofill import autofill_application_questions, build_application_profile
from utils.job_intelligence import extract_job_text, find_external_links, keyword_match
from utils.tracker import is_duplicate_application, log_application, log_external_link


class IndeedBot:
    def __init__(self, config: dict):
        self.email = config["platforms"]["indeed"]["email"]
        self.password = config["platforms"]["indeed"]["password"]
        self.job_titles = config["job_titles"]
        self.locations = config["locations"]
        self.delay = config["delay_between_actions"]
        self.delay_jitter_min = float(config.get("delay_jitter_min", 0.8))
        self.delay_jitter_max = float(config.get("delay_jitter_max", 2.0))
        self.max_apps = config["max_applications_per_day"]
        self.applied_count = 0
        self.base_url = "https://in.indeed.com"
        self.platform_name = "Indeed"
        self.dry_run = bool(config.get("dry_run", False))
        self.application_profile = build_application_profile(config)
        self.requirement_keywords = list(config.get("requirement_keywords", []))
        self.min_keyword_matches = int(config.get("min_keyword_matches", 1))
        self.platform_domains = ["indeed.com"]
        self.max_external_links = int(config.get("max_external_links_per_job", 2))

    async def login(self, page: Page):
        print("Indeed login started")
        try:
            for attempt in range(1, 3):
                await safe_goto(page, f"{self.base_url}/account/login")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

                email_ok = await safe_fill(page, ["input[name='__email']", "input[type='email']"], self.email)
                if email_ok:
                    await page.keyboard.press("Enter")
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

                password_ok = await safe_fill(
                    page,
                    ["input[name='__password']", "input[type='password']"],
                    self.password,
                )
                if password_ok:
                    await page.keyboard.press("Enter")
                    await human_pause(self.delay + 1, self.delay_jitter_min, self.delay_jitter_max)

                account_badge = await first_visible(
                    page,
                    ["a[data-testid='AccountMenu']", "button[aria-label*='Account']", "a[href*='/account']"],
                )
                if "account/login" not in page.url or account_badge:
                    print("Indeed login successful")
                    return True
                print(f"Indeed login retry {attempt}/2")
            print("Indeed login failed")
            return False
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "login", exc)
            print(f"Indeed login error: {exc}")
            return False

    async def search_and_apply(self, page: Page, job_title: str, location: str):
        print(f"Indeed search: {job_title} in {location}")
        search_url = f"{self.base_url}/jobs?q={job_title.replace(' ', '+')}&l={location.replace(' ', '+')}"

        try:
            await safe_goto(page, search_url)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
            jobs = await page.query_selector_all("div.job_seen_beacon")
            print(f"Indeed listings found: {len(jobs)}")

            for job in jobs[:5]:
                if self.applied_count >= self.max_apps:
                    break

                title_el = await first_visible(job, ["h2.jobTitle span", "h2 a span"])
                company_el = await first_visible(job, ["span.companyName"])
                location_el = await first_visible(job, ["div.companyLocation"])
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                location_text = (await location_el.inner_text()).strip() if location_el else location

                await title_el.click()
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                job_url = page.url

                if is_duplicate_application(self.platform_name, company, title, job_url):
                    print(f"Skipped duplicate: {company} - {title}")
                    continue

                job_text = await extract_job_text(page)
                is_match, matched_keywords = keyword_match(
                    job_text, self.requirement_keywords, self.min_keyword_matches
                )
                if not is_match:
                    log_application(
                        self.platform_name,
                        company,
                        title,
                        location_text,
                        status="Skipped - Keyword Mismatch",
                        job_url=job_url,
                        notes="No required keyword found",
                    )
                    print(f"Skipped keyword mismatch: {company} - {title}")
                    continue

                external_links = await find_external_links(page, self.platform_domains)
                for external_url in external_links[: self.max_external_links]:
                    handled, applied, message = await handle_external_link(page, external_url, dry_run=self.dry_run)
                    log_external_link(
                        self.platform_name,
                        company,
                        title,
                        job_url,
                        external_url,
                        handled=handled,
                        applied=applied,
                        notes=f"{message} | Matched keywords: " + ", ".join(matched_keywords[:8]),
                    )

                if self.dry_run:
                    log_application(
                        self.platform_name,
                        company,
                        title,
                        location_text,
                        status="Dry Run",
                        job_url=job_url,
                        notes="Matched keywords: " + ", ".join(matched_keywords[:8]),
                    )
                    print(f"Dry run logged: {company} - {title}")
                    continue

                apply_btn = await first_visible(
                    page,
                    ["button.ia-IndeedApplyButton", "button:has-text('Apply Now')", "button:has-text('Apply')"],
                )
                if not apply_btn:
                    continue

                await apply_btn.click()
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

                for _ in range(5):
                    filled_count = await autofill_application_questions(page, self.application_profile)
                    if filled_count:
                        print(f"Indeed autofilled {filled_count} fields")

                    next_btn = await first_visible(
                        page,
                        [
                            "button[aria-label='Continue to next step']",
                            "button:has-text('Continue')",
                            "button:has-text('Next')",
                        ],
                    )
                    if not next_btn:
                        break
                    await next_btn.click()
                    await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)

                filled_count = await autofill_application_questions(page, self.application_profile)
                if filled_count:
                    print(f"Indeed autofilled {filled_count} fields")

                submit_btn = await first_visible(
                    page,
                    ["button[aria-label='Submit your application']", "button:has-text('Submit')"],
                )
                if not submit_btn:
                    continue

                await submit_btn.click()
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                self.applied_count += 1
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location_text,
                    status="Applied",
                    job_url=job_url,
                    notes="Matched keywords: " + ", ".join(matched_keywords[:8]),
                )
                print(f"Indeed applied: {company} - {title}")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "search_and_apply", exc)
            print(f"Indeed search/apply error: {exc}")

    async def run(self, page: Page):
        print("Indeed bot starting")
        if not await self.login(page):
            return

        for job_title in self.job_titles:
            for location in self.locations[:2]:
                if self.applied_count >= self.max_apps:
                    break
                await self.search_and_apply(page, job_title, location)
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

        print(f"Indeed bot done. Applied: {self.applied_count}")


class ApnaBot:
    def __init__(self, config: dict):
        self.phone = config["platforms"]["apna"]["phone"]
        self.job_titles = config["job_titles"]
        self.delay = config["delay_between_actions"]
        self.delay_jitter_min = float(config.get("delay_jitter_min", 0.8))
        self.delay_jitter_max = float(config.get("delay_jitter_max", 2.0))
        self.otp_wait_seconds = int(config.get("otp_wait_seconds", 90))
        self.max_apps = config["max_applications_per_day"]
        self.applied_count = 0
        self.base_url = "https://apna.co"
        self.platform_name = "Apna"
        self.dry_run = bool(config.get("dry_run", False))
        self.application_profile = build_application_profile(config)
        self.requirement_keywords = list(config.get("requirement_keywords", []))
        self.min_keyword_matches = int(config.get("min_keyword_matches", 1))
        self.platform_domains = ["apna.co"]
        self.max_external_links = int(config.get("max_external_links_per_job", 2))

    async def login(self, page: Page):
        print("Apna login started")
        try:
            await safe_goto(page, f"{self.base_url}/jobs")
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

            await safe_click(page, ["button:has-text('Login')", "button:has-text('Sign in')"])
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

            phone_ok = await safe_fill(page, ["input[type='tel']", "input[name='mobile']"], self.phone)
            if not phone_ok:
                print("Apna phone input not found")
                return False

            otp_btn = await safe_click(page, ["button:has-text('Send OTP')", "button:has-text('Continue')"])
            if not otp_btn:
                print("Apna OTP button not found")
                return False

            print(f"OTP sent. Enter OTP manually in browser window (wait up to {self.otp_wait_seconds}s).")
            checks = max(1, self.otp_wait_seconds // 3)
            for _ in range(checks):
                login_inputs = await first_visible(page, ["input[type='tel']", "button:has-text('Send OTP')"])
                if not login_inputs:
                    print("Apna login successful")
                    return True
                await asyncio.sleep(3)

            print("Apna login timeout")
            return False
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "login", exc)
            print(f"Apna login error: {exc}")
            return False

    async def search_and_apply(self, page: Page, job_title: str):
        print(f"Apna search: {job_title}")
        try:
            search_ok = await safe_fill(
                page,
                ["input[placeholder*='job']", "input[placeholder*='Search']"],
                job_title,
            )
            if search_ok:
                await page.keyboard.press("Enter")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

            jobs = await page.query_selector_all(".job-card, .job-listing")
            print(f"Apna listings found: {len(jobs)}")

            for job in jobs[:4]:
                if self.applied_count >= self.max_apps:
                    break

                title_el = await first_visible(job, ["h2", ".job-title"])
                company_el = await first_visible(job, [".company-name", ".company"])
                title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"

                await job.click()
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                job_url = page.url

                if is_duplicate_application(self.platform_name, company, title, job_url):
                    print(f"Skipped duplicate: {company} - {title}")
                    if "apna.co/jobs" not in page.url:
                        await page.go_back()
                        await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                    continue

                job_text = await extract_job_text(page)
                is_match, matched_keywords = keyword_match(
                    job_text, self.requirement_keywords, self.min_keyword_matches
                )
                if not is_match:
                    log_application(
                        self.platform_name,
                        company,
                        title,
                        "",
                        status="Skipped - Keyword Mismatch",
                        job_url=job_url,
                        notes="No required keyword found",
                    )
                    print(f"Skipped keyword mismatch: {company} - {title}")
                    if "apna.co/jobs" not in page.url:
                        await page.go_back()
                        await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                    continue

                external_links = await find_external_links(page, self.platform_domains)
                for external_url in external_links[: self.max_external_links]:
                    handled, applied, message = await handle_external_link(page, external_url, dry_run=self.dry_run)
                    log_external_link(
                        self.platform_name,
                        company,
                        title,
                        job_url,
                        external_url,
                        handled=handled,
                        applied=applied,
                        notes=f"{message} | Matched keywords: " + ", ".join(matched_keywords[:8]),
                    )

                if self.dry_run:
                    log_application(
                        self.platform_name,
                        company,
                        title,
                        "",
                        status="Dry Run",
                        job_url=job_url,
                        notes="Matched keywords: " + ", ".join(matched_keywords[:8]),
                    )
                    print(f"Dry run logged: {company} - {title}")
                    if "apna.co/jobs" not in page.url:
                        await page.go_back()
                        await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                    continue

                apply_btn = await first_visible(page, ["button:has-text('Apply')", "button:has-text('Apply Now')"])
                if apply_btn:
                    await apply_btn.click()
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

                    for _ in range(3):
                        filled_count = await autofill_application_questions(page, self.application_profile)
                        if filled_count:
                            print(f"Apna autofilled {filled_count} fields")

                        step_btn = await first_visible(
                            page,
                            [
                                "button:has-text('Continue')",
                                "button:has-text('Next')",
                                "button:has-text('Submit')",
                                "button:has-text('Apply')",
                            ],
                        )
                        if not step_btn:
                            break
                        await step_btn.click()
                        await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)

                    self.applied_count += 1
                    log_application(
                        self.platform_name,
                        company,
                        title,
                        "",
                        status="Applied",
                        job_url=job_url,
                        notes="Matched keywords: " + ", ".join(matched_keywords[:8]),
                    )
                    print(f"Apna applied: {company} - {title}")

                if "apna.co/jobs" not in page.url:
                    await page.go_back()
                    await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
        except Exception as exc:  # noqa: BLE001
            await capture_failure(page, self.platform_name, "search_and_apply", exc)
            print(f"Apna search/apply error: {exc}")

    async def run(self, page: Page):
        print("Apna bot starting")
        if not await self.login(page):
            return

        for job_title in self.job_titles:
            if self.applied_count >= self.max_apps:
                break
            await self.search_and_apply(page, job_title)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

        print(f"Apna bot done. Applied: {self.applied_count}")
