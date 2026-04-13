"""Helpers to auto-fill common job application form questions."""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import ElementHandle, Page


_KEYWORD_TO_PROFILE_FIELD: list[tuple[tuple[str, ...], str]] = [
    (("current company", "present company", "current employer", "employer"), "current_company"),
    (
        ("current job title", "current role", "designation", "job title", "role"),
        "current_job_title",
    ),
    (("employment status", "currently working"), "employment_status"),
    (("qualification", "highest qualification", "degree"), "qualification"),
    (("specialization", "branch", "stream"), "specialization"),
    (("education", "educational qualification"), "education"),
    (("cgpa", "gpa"), "cgpa"),
    (("college", "institute"), "college"),
    (("university",), "university"),
    (("10th", "class 10", "ssc"), "tenth_percentage"),
    (("12th", "class 12", "hsc"), "twelfth_percentage"),
    (("source", "how did you hear", "reference source"), "source"),
    (("current location", "location", "city"), "location"),
    (("graduation year", "passing year", "year of graduation"), "graduation_year"),
    (("experience", "years of experience"), "experience_years"),
    (("expected salary", "ctc", "salary expectation"), "expected_salary"),
    (("notice period",), "notice_period_days"),
    (("full name", "your name", "name"), "name"),
    (("email",), "email"),
    (("phone", "mobile"), "phone"),
    (("linkedin", "linkedin profile"), "linkedin_url"),
    (("github", "github profile"), "github_url"),
]

_SKIP_CONTEXT_KEYWORDS = (
    "password",
    "otp",
    "search",
    "captcha",
    "verification code",
)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def build_application_profile(config: dict[str, Any]) -> dict[str, str]:
    profile = dict(config.get("application_profile", {}))

    if not profile.get("name"):
        profile["name"] = str(config.get("name", "")).strip()
    if not profile.get("email"):
        profile["email"] = str(config.get("email", "")).strip()
    if not profile.get("phone"):
        profile["phone"] = str(config.get("phone", "")).strip()
    if not profile.get("location"):
        profile["location"] = str((config.get("locations") or [""])[0]).strip()
    if not profile.get("experience_years"):
        profile["experience_years"] = str(config.get("experience_years", "")).strip()
    if not profile.get("expected_salary"):
        profile["expected_salary"] = str(config.get("expected_salary", "")).strip()

    return {key: str(val).strip() for key, val in profile.items() if val is not None}


async def _field_context(page: Page, field: ElementHandle) -> str:
    parts: list[str] = []

    for attr in ("name", "id", "placeholder", "aria-label"):
        val = await field.get_attribute(attr)
        if val:
            parts.append(val)

    try:
        label = await field.evaluate(
            """(el) => {
                const direct = el.closest('label');
                if (direct) return direct.innerText || '';
                const id = el.getAttribute('id');
                if (id) {
                    const forLabel = document.querySelector(`label[for="${id}"]`);
                    if (forLabel) return forLabel.innerText || '';
                }
                const row = el.closest('div, section, form');
                if (!row) return '';
                const prompt = row.querySelector('label, legend, .question, .question-text');
                return prompt ? (prompt.innerText || '') : '';
            }"""
        )
        if label:
            parts.append(str(label))
    except Exception:  # noqa: BLE001
        pass

    return _norm(" ".join(parts))


def _pick_value(context: str, profile: dict[str, str]) -> str | None:
    if not context:
        return None
    if any(skip_word in context for skip_word in _SKIP_CONTEXT_KEYWORDS):
        return None

    for keywords, profile_key in _KEYWORD_TO_PROFILE_FIELD:
        if profile_key not in profile or not profile[profile_key]:
            continue
        if any(keyword in context for keyword in keywords):
            return profile[profile_key]
    return None


async def _fill_select(field: ElementHandle, value: str) -> bool:
    try:
        await field.select_option(label=value)
        return True
    except Exception:  # noqa: BLE001
        pass

    try:
        await field.select_option(value=value)
        return True
    except Exception:  # noqa: BLE001
        return False


async def autofill_application_questions(page: Page, profile: dict[str, str]) -> int:
    """Fill known question fields in the current application page/modal."""
    if not profile:
        return 0

    filled = 0
    fields = await page.query_selector_all("input, textarea, select")
    for field in fields:
        is_disabled = await field.is_disabled()
        if is_disabled:
            continue

        tag_name = _norm(await field.evaluate("el => el.tagName"))
        input_type = _norm(await field.get_attribute("type") or "")
        if input_type in {"hidden", "file", "checkbox", "radio"}:
            continue

        current_val = _norm(await field.input_value() if tag_name != "select" else "")
        if current_val:
            continue

        context = await _field_context(page, field)
        value = _pick_value(context, profile)
        if not value:
            continue

        if tag_name == "select":
            ok = await _fill_select(field, value)
        else:
            try:
                await field.fill(value)
                ok = True
            except Exception:  # noqa: BLE001
                ok = False

        if ok:
            filled += 1

    return filled
