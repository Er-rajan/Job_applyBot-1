"""Indeed and Apna bots."""

import asyncio

from playwright.async_api import Page

from utils.application_quality import (
    ApplicationStateMachine,
    detect_submit_confirmation,
    dismiss_common_popups,
    validate_required_fields,
)
from utils.browser_utils import capture_failure, first_visible, human_pause, safe_click, safe_fill, safe_goto
from utils.external_apply import handle_external_link
from utils.form_autofill import (
    autofill_application_questions,
    autofill_with_question_bank,
    build_application_profile,
    build_question_bank,
    save_question_bank,
)
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
        self.validate_mode = bool(config.get("validate_mode", False))
        self.force_apply_mode = bool(config.get("force_apply_mode", False))
        self.application_profile = build_application_profile(config)
        self.requirement_keywords = list(config.get("requirement_keywords", []))
        self.min_keyword_matches = int(config.get("min_keyword_matches", 1))
        self.platform_domains = ["indeed.com"]
        self.max_external_links = int(config.get("max_external_links_per_job", 2))
        self.max_jobs_per_search = int(config.get("max_jobs_per_search", 8))
        self.login_retry_attempts = int(config.get("login_retry_attempts", 3))
        self.question_bank_path = str(config.get("question_bank_path", "data/application_question_bank.json"))
        self.question_bank = build_question_bank(config, self.question_bank_path)
        self.accuracy = dict(config.get("accuracy", {}))
        self.block_on_todo_answer = bool(self.accuracy.get("block_on_todo_answer", True))
        self.require_submit_confirmation = bool(self.accuracy.get("require_submit_confirmation", True))
        selectors_cfg = dict(config.get("platform_selectors", {}))
        self.popup_selectors = list(selectors_cfg.get("common_popup_close", []))
        self.success_markers = list(selectors_cfg.get("indeed_success", []))

    async def login(self, page: Page):
        print("Indeed login started")
        last_error = "Unknown"
        for attempt in range(1, self.login_retry_attempts + 1):
            try:
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
                last_error = f"Still on login page URL: {page.url}"
                print(f"Indeed login retry {attempt}/{self.login_retry_attempts}: {last_error}")
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                print(f"Indeed login attempt {attempt}/{self.login_retry_attempts} error: {last_error}")
                await capture_failure(page, self.platform_name, f"login_attempt_{attempt}", exc)
        print(f"Indeed login failed after {self.login_retry_attempts} attempts. Reason: {last_error}")
        return False

    async def search_and_apply(self, page: Page, job_title: str, location: str):
        print(f"Indeed search: {job_title} in {location}")
        search_url = f"{self.base_url}/jobs?q={job_title.replace(' ', '+')}&l={location.replace(' ', '+')}"

        try:
            await safe_goto(page, search_url)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
            jobs = await page.query_selector_all("div.job_seen_beacon")
            total_jobs = len(jobs)
            print(f"Indeed listings found: {total_jobs}")

            for idx in range(min(total_jobs, self.max_jobs_per_search)):
                if self.applied_count >= self.max_apps:
                    break
                try:
                    jobs = await page.query_selector_all("div.job_seen_beacon")
                    if idx >= len(jobs):
                        break
                    job = jobs[idx]
                    title_el = await first_visible(job, ["h2.jobTitle span", "h2 a span"])
                    company_el = await first_visible(job, ["span.companyName"])
                    location_el = await first_visible(job, ["div.companyLocation"])
                    if not title_el:
                        continue

                    title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                    company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                    location_text = (await location_el.inner_text()).strip() if location_el else location
                    flow = ApplicationStateMachine(self.platform_name, company, title)

                    card_link = await first_visible(
                        job,
                        [
                            "h2.jobTitle a",
                            "a.jcs-JobTitle",
                            "a[data-jk]",
                        ],
                    )
                    clicked = False
                    if card_link:
                        try:
                            await card_link.click()
                            clicked = True
                        except Exception:  # noqa: BLE001
                            clicked = False
                    if not clicked:
                        await job.click()
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                    job_url = page.url
                    if "/jobs?" in job_url or job_url.rstrip("/") == f"{self.base_url}/jobs":
                        direct_link = await first_visible(job, ["h2.jobTitle a", "a.jcs-JobTitle", "a[data-jk]"])
                        href = await direct_link.get_attribute("href") if direct_link else None
                        if href:
                            job_url = href if href.startswith("http") else f"{self.base_url}{href}"
                    flow.transition("job-opened")

                    if (not self.force_apply_mode) and is_duplicate_application(self.platform_name, company, title, job_url):
                        print(f"Skipped duplicate: {company} - {title}")
                        continue

                    job_text = await extract_job_text(page)
                    is_match, matched_keywords = keyword_match(job_text, self.requirement_keywords, self.min_keyword_matches)
                    if (not self.force_apply_mode) and (not is_match):
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            location_text,
                            status="Skipped - Keyword Mismatch",
                            job_url=job_url,
                            notes="No required keyword found",
                        )
                        continue

                    if self.dry_run and (not self.validate_mode):
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            location_text,
                            status="Dry Run",
                            job_url=job_url,
                            notes="Matched keywords: " + ", ".join(matched_keywords[:8]),
                        )
                        continue

                    apply_btn = await first_visible(
                        page,
                        ["button.ia-IndeedApplyButton", "button:has-text('Apply Now')", "button:has-text('Apply')"],
                    )
                    if not apply_btn:
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            location_text,
                            status="Failed - Apply Button Missing",
                            job_url=job_url,
                            notes=f"Flow: {flow.summary()}",
                        )
                        continue

                    await apply_btn.click()
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                    await dismiss_common_popups(page, self.popup_selectors, max_rounds=2)
                    flow.transition("apply-clicked")

                    for _ in range(10):
                        await page.mouse.wheel(0, 700)
                        await human_pause(1, self.delay_jitter_min, self.delay_jitter_max)
                        _, _, unknown_questions = await autofill_with_question_bank(
                            page,
                            self.application_profile,
                            self.question_bank,
                        )
                        if unknown_questions:
                            for question in unknown_questions[:5]:
                                self.question_bank.setdefault(question, "TODO_ANSWER")
                        save_question_bank(self.question_bank_path, self.question_bank)

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
                        await human_pause(2, self.delay_jitter_min, self.delay_jitter_max)
                    flow.transition("questions-filled")

                    await page.mouse.wheel(0, 1400)
                    await human_pause(3, self.delay_jitter_min, self.delay_jitter_max)

                    ready, issues = await validate_required_fields(page)
                    if not ready:
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            location_text,
                            status="Blocked - Incomplete Form",
                            job_url=job_url,
                            notes=" | ".join(issues[:5]) + f" | Flow: {flow.summary()}",
                        )
                        continue

                    if self.validate_mode:
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            location_text,
                            status="Validated - No Submit",
                            job_url=job_url,
                            notes=f"Validate mode | Flow: {flow.summary()}",
                        )
                        continue

                    submit_btn = await first_visible(
                        page,
                        [
                            "button[aria-label='Submit your application']",
                            "button:has-text('Submit your application')",
                            "button:has-text('Submit')",
                        ],
                    )
                    if not submit_btn:
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            location_text,
                            status="Failed - Submit Button Missing",
                            job_url=job_url,
                            notes=f"Flow: {flow.summary()}",
                        )
                        continue

                    await submit_btn.click()
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                    confirmed = True
                    if self.require_submit_confirmation:
                        confirmed = await detect_submit_confirmation(
                            page,
                            success_selectors=["text=Application submitted", "text=Thanks for applying"],
                            success_text_markers=self.success_markers,
                        )
                    status = "Applied" if confirmed else "Submitted - Unconfirmed"
                    if confirmed:
                        self.applied_count += 1
                    flow.transition(status.lower().replace(" ", "-"))
                    log_application(
                        self.platform_name,
                        company,
                        title,
                        location_text,
                        status=status,
                        job_url=job_url,
                        notes="Matched keywords: " + ", ".join(matched_keywords[:8]) + f" | Flow: {flow.summary()}",
                    )
                except Exception as job_exc:  # noqa: BLE001
                    print(f"Indeed job #{idx + 1} failed, continuing: {type(job_exc).__name__}: {job_exc}")
                    await capture_failure(page, self.platform_name, f"job_loop_{idx + 1}", job_exc)
                    continue
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
        self.force_apply_mode = bool(config.get("force_apply_mode", False))
        self.application_profile = build_application_profile(config)
        self.requirement_keywords = list(config.get("requirement_keywords", []))
        self.min_keyword_matches = int(config.get("min_keyword_matches", 1))
        self.platform_domains = ["apna.co"]
        self.max_external_links = int(config.get("max_external_links_per_job", 2))
        self.max_jobs_per_search = int(config.get("max_jobs_per_search", 8))

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

            for idx, job in enumerate(jobs[: self.max_jobs_per_search], start=1):
                if self.applied_count >= self.max_apps:
                    break
                try:
                    title_el = await first_visible(job, ["h2", ".job-title"])
                    company_el = await first_visible(job, [".company-name", ".company"])
                    title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

                    await job.click()
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
                    job_url = page.url

                    if (not self.force_apply_mode) and is_duplicate_application(self.platform_name, company, title, job_url):
                        if "apna.co/jobs" not in page.url:
                            await page.go_back()
                            await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                        continue

                    job_text = await extract_job_text(page)
                    is_match, matched_keywords = keyword_match(job_text, self.requirement_keywords, self.min_keyword_matches)
                    if (not self.force_apply_mode) and (not is_match):
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            "",
                            status="Skipped - Keyword Mismatch",
                            job_url=job_url,
                            notes="No required keyword found",
                        )
                        if "apna.co/jobs" not in page.url:
                            await page.go_back()
                            await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                        continue

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
                        if "apna.co/jobs" not in page.url:
                            await page.go_back()
                            await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                        continue

                    apply_btn = await first_visible(page, ["button:has-text('Apply')", "button:has-text('Apply Now')"])
                    if not apply_btn:
                        log_application(
                            self.platform_name,
                            company,
                            title,
                            "",
                            status="Failed - Apply Button Missing",
                            job_url=job_url,
                            notes=f"Force mode={self.force_apply_mode}",
                        )
                        if "apna.co/jobs" not in page.url:
                            await page.go_back()
                        continue

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

                    if "apna.co/jobs" not in page.url:
                        await page.go_back()
                        await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)
                except Exception as job_exc:  # noqa: BLE001
                    print(f"Apna job #{idx} failed, continuing: {type(job_exc).__name__}: {job_exc}")
                    await capture_failure(page, self.platform_name, f"job_loop_{idx}", job_exc)
                    if "apna.co/jobs" not in page.url:
                        try:
                            await page.go_back()
                        except Exception:  # noqa: BLE001
                            pass
                    continue
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
