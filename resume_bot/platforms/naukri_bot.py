"""Naukri bot."""

import asyncio
from urllib.parse import quote_plus

from playwright.async_api import Page

from utils.application_quality import (
    ApplicationStateMachine,
    detect_submit_confirmation,
    dismiss_common_popups,
    find_best_question_answer,
    normalize_text,
    run_step_with_retry,
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


class NaukriBot:
    def __init__(self, config: dict):
        self.email = config["platforms"]["naukri"]["email"]
        self.password = config["platforms"]["naukri"]["password"]
        self.job_titles = config["job_titles"]
        self.locations = config["locations"]
        self.delay = config["delay_between_actions"]
        self.delay_jitter_min = float(config.get("delay_jitter_min", 0.8))
        self.delay_jitter_max = float(config.get("delay_jitter_max", 2.0))
        self.max_apps = config["max_applications_per_day"]
        self.applied_count = 0
        self.base_url = "https://www.naukri.com"
        self.platform_name = "Naukri"
        self.dry_run = bool(config.get("dry_run", False))
        self.validate_mode = bool(config.get("validate_mode", False))
        self.force_apply_mode = bool(config.get("force_apply_mode", False))
        self.application_profile = build_application_profile(config)
        self.requirement_keywords = list(config.get("requirement_keywords", []))
        self.min_keyword_matches = int(config.get("min_keyword_matches", 1))
        self.platform_domains = ["naukri.com"]
        self.max_external_links = int(config.get("max_external_links_per_job", 2))
        self.max_jobs_per_search = int(config.get("max_jobs_per_search", 8))
        self.login_retry_attempts = int(config.get("login_retry_attempts", 3))
        self.question_bank_path = str(config.get("question_bank_path", "data/application_question_bank.json"))
        self.question_bank = build_question_bank(config, self.question_bank_path)
        self.accuracy = dict(config.get("accuracy", {}))
        self.max_step_retries = int(self.accuracy.get("max_step_retries", 2))
        self.block_on_todo_answer = bool(self.accuracy.get("block_on_todo_answer", True))
        self.require_submit_confirmation = bool(self.accuracy.get("require_submit_confirmation", True))
        selectors_cfg = dict(config.get("platform_selectors", {}))
        self.popup_selectors = list(selectors_cfg.get("common_popup_close", []))
        self.success_markers = list(selectors_cfg.get("naukri_success", []))

    async def _dismiss_naukri_popups(self, page: Page) -> bool:
        """Close blocking ad/popups if visible."""
        dismissed = await dismiss_common_popups(
            page,
            self.popup_selectors
            + [".chatbot_cross", ".chatbot-close", ".notification-cross", "button:has-text('No Thanks')"],
            max_rounds=3,
        )
        if dismissed:
            await human_pause(0.5, self.delay_jitter_min, self.delay_jitter_max)
        return dismissed > 0

    async def _fill_naukri_question_chat(self, page: Page) -> int:
        """Answer recruiter chat-style questions and click Save."""
        answered = 0
        for _ in range(8):
            # Try regular form autofill first.
            filled_count, learned_count, unknown_questions = await autofill_with_question_bank(
                page, self.application_profile, self.question_bank
            )
            answered += filled_count
            if learned_count:
                print(f"Naukri learned {learned_count} question mappings")
            if unknown_questions:
                for question in unknown_questions[:10]:
                    self.question_bank.setdefault(question, "TODO_ANSWER")
                save_question_bank(self.question_bank_path, self.question_bank)

            # Handle chat input where one question appears at a time.
            question_el = await first_visible(
                page,
                [
                    ".chatbot_MessageContainer .message",
                    ".chatbot .bot-message",
                    ".question-text",
                    "div:has-text('What is your')",
                    "div:has-text('How many years')",
                    "div:has-text('Are you')",
                ],
            )
            chat_input = await first_visible(
                page,
                [
                    "input[placeholder*='Type message']",
                    "textarea[placeholder*='Type message']",
                    "input[placeholder*='message']",
                    "textarea[placeholder*='message']",
                ],
            )

            if question_el and chat_input:
                question_txt = (await question_el.inner_text()).strip().lower()
                question_key = normalize_text(question_txt)
                answer = find_best_question_answer(question_key, self.question_bank, threshold=0.68)
                if not answer:
                    self.question_bank.setdefault(question_key, "TODO_ANSWER")
                    save_question_bank(self.question_bank_path, self.question_bank)
                    answer = "TODO_ANSWER"
                if self.block_on_todo_answer and answer == "TODO_ANSWER":
                    print(f"Naukri blocked submit due to unanswered question: {question_key}")
                    break

                try:
                    await chat_input.fill(answer)
                    await page.keyboard.press("Enter")
                    answered += 1
                    await human_pause(1, self.delay_jitter_min, self.delay_jitter_max)
                except Exception:  # noqa: BLE001
                    pass

            save_btn = await first_visible(
                page,
                [
                    "button:has-text('Save')",
                    "button:has-text('Submit')",
                    "button:has-text('Continue')",
                ],
            )
            if save_btn:
                try:
                    await save_btn.click()
                    await human_pause(1, self.delay_jitter_min, self.delay_jitter_max)
                except Exception:  # noqa: BLE001
                    pass
            else:
                break

        save_question_bank(self.question_bank_path, self.question_bank)
        return answered

    async def login(self, page: Page):
        print("Naukri login started")
        last_error = "Unknown"
        for attempt in range(1, self.login_retry_attempts + 1):
            try:
                await safe_goto(page, f"{self.base_url}/nlogin/login")
                await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

                email_ok = await safe_fill(
                    page,
                    [
                        "input[placeholder='Enter your active Email ID / Username']",
                        "input[placeholder*='Email ID']",
                        "input[placeholder*='Username']",
                        "input[name='username']",
                        "input[id*='username']",
                        "input[id*='email']",
                        "input[type='email']",
                    ],
                    self.email,
                )
                if not email_ok:
                    # Fallback: try first visible text/email input in the login form only.
                    login_form_input = await first_visible(
                        page,
                        [
                            "form input[type='email']",
                            "form input[name='username']",
                            "form input[placeholder*='Email']",
                            "form input[placeholder*='Username']",
                        ],
                    )
                    if login_form_input:
                        try:
                            await login_form_input.fill(self.email)
                            email_ok = True
                        except Exception:  # noqa: BLE001
                            email_ok = False
                password_ok = await safe_fill(
                    page,
                    ["input[placeholder='Enter your password']", "input[type='password']"],
                    self.password,
                )
                submit_ok = await safe_click(page, ["button[type='submit']"])

                if not (email_ok and password_ok and submit_ok):
                    last_error = "Login form elements not found"
                    print(f"Naukri login attempt {attempt}/{self.login_retry_attempts} failed: {last_error}")
                    continue

                await human_pause(self.delay + 1, self.delay_jitter_min, self.delay_jitter_max)
                profile_hint = await first_visible(page, [".nI-gNb-drawer", ".view-profile-wrapper"])
                if "login" not in page.url or profile_hint:
                    print("Naukri login successful")
                    return True
                last_error = f"Still on login page URL: {page.url}"
                print(f"Naukri login retry {attempt}/{self.login_retry_attempts}: {last_error}")
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                print(f"Naukri login attempt {attempt}/{self.login_retry_attempts} error: {last_error}")
                await capture_failure(page, self.platform_name, f"login_attempt_{attempt}", exc)
        print(f"Naukri login failed after {self.login_retry_attempts} attempts. Reason: {last_error}")
        return False

    async def search_jobs(self, page: Page, job_title: str, location: str):
        print(f"Naukri search: {job_title} in {location}")
        slug_title = quote_plus(job_title).replace("+", "-")
        slug_location = quote_plus(location).replace("+", "-")
        search_url = f"{self.base_url}/{slug_title}-jobs-in-{slug_location}"

        try:
            await safe_goto(page, search_url)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
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
            flow = ApplicationStateMachine(self.platform_name, company, title)
            flow.transition("opened-listing")

            before_pages = list(page.context.pages)
            async def _open_job() -> bool:
                await title_el.click()
                return True

            await run_step_with_retry("open-job", _open_job, retries=self.max_step_retries)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
            after_pages = list(page.context.pages)
            job_page = after_pages[-1] if len(after_pages) > len(before_pages) else page
            job_url = job_page.url
            flow.transition("job-opened")

            if not self.force_apply_mode and is_duplicate_application(self.platform_name, company, title, job_url):
                print(f"Skipped duplicate: {company} - {title}")
                if job_page != page:
                    await job_page.close()
                return False

            job_text = await extract_job_text(job_page)
            is_match, matched_keywords = keyword_match(job_text, self.requirement_keywords, self.min_keyword_matches)
            if not self.force_apply_mode and not is_match:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location,
                    status="Skipped - Keyword Mismatch",
                    job_url=job_url,
                    notes="No required keyword found",
                )
                print(f"Skipped keyword mismatch: {company} - {title}")
                if job_page != page:
                    await job_page.close()
                return False

            external_links = await find_external_links(job_page, self.platform_domains)
            for external_url in external_links[: self.max_external_links]:
                handled, applied, message = await handle_external_link(job_page, external_url, dry_run=self.dry_run)
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

            if self.dry_run and not self.validate_mode:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location,
                    status="Dry Run",
                    job_url=job_url,
                    notes="Matched keywords: " + ", ".join(matched_keywords[:8]),
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
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location,
                    status="Failed - Apply Button Missing",
                    job_url=job_url,
                    notes=f"Flow: {flow.summary()}",
                )
                if job_page != page:
                    await job_page.close()
                return False

            await self._dismiss_naukri_popups(job_page)
            flow.transition("apply-found")
            async def _click_apply() -> bool:
                await apply_btn.click()
                return True

            await run_step_with_retry("click-apply", _click_apply, retries=self.max_step_retries)
            await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)
            await self._dismiss_naukri_popups(job_page)
            flow.transition("apply-clicked")

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
                await human_pause(self.delay / 2, self.delay_jitter_min, self.delay_jitter_max)

            await job_page.mouse.wheel(0, 1200)
            await human_pause(1, self.delay_jitter_min, self.delay_jitter_max)
            qa_answered = await self._fill_naukri_question_chat(job_page)
            if qa_answered:
                print(f"Naukri answered {qa_answered} recruiter questions")
            flow.transition("questions-filled")

            ready, issues = await validate_required_fields(job_page)
            if not ready:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location,
                    status="Blocked - Incomplete Form",
                    job_url=job_url,
                    notes=" | ".join(issues[:5]) + f" | Flow: {flow.summary()}",
                )
                if job_page != page:
                    await job_page.close()
                return False
            if self.validate_mode:
                log_application(
                    self.platform_name,
                    company,
                    title,
                    location,
                    status="Validated - No Submit",
                    job_url=job_url,
                    notes=f"Validate mode | Flow: {flow.summary()}",
                )
                if job_page != page:
                    await job_page.close()
                return True

            already_applied = await job_page.query_selector("text=already applied")
            if already_applied:
                status = "Already Applied"
            else:
                confirmed = True
                if self.require_submit_confirmation:
                    confirmed = await detect_submit_confirmation(
                        job_page,
                        success_selectors=["text=already applied", "text=Application sent", "text=Successfully"],
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
                location,
                status=status,
                job_url=job_url,
                notes="Matched keywords: " + ", ".join(matched_keywords[:8]) + f" | Flow: {flow.summary()}",
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
                for card in cards[: self.max_jobs_per_search]:
                    if self.applied_count >= self.max_apps:
                        break
                    await self.apply_to_job(page, card)
                    await human_pause(self.delay, self.delay_jitter_min, self.delay_jitter_max)

        print(f"Naukri bot done. Applied: {self.applied_count}")
