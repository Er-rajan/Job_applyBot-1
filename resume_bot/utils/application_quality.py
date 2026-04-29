"""Shared accuracy helpers for multi-step application bots."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Awaitable, Callable

from playwright.async_api import Page


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def find_best_question_answer(question: str, question_bank: dict[str, str], threshold: float = 0.72) -> str | None:
    q = normalize_text(question)
    if not q:
        return None

    direct = question_bank.get(q)
    if direct:
        return direct

    best_key = None
    best_score = 0.0
    for key in question_bank:
        score = SequenceMatcher(None, q, normalize_text(key)).ratio()
        if score > best_score:
            best_score = score
            best_key = key
    if best_key and best_score >= threshold:
        return question_bank.get(best_key)
    return None


async def dismiss_common_popups(page: Page, selectors: list[str], max_rounds: int = 3) -> int:
    dismissed = 0
    for _ in range(max_rounds):
        clicked_any = False
        for selector in selectors:
            el = await page.query_selector(selector)
            if not el:
                continue
            if not await el.is_visible():
                continue
            try:
                await el.click()
                dismissed += 1
                clicked_any = True
                await asyncio.sleep(0.25)
            except Exception:  # noqa: BLE001
                pass
        if not clicked_any:
            break
    return dismissed


async def run_step_with_retry(step_name: str, action: Callable[[], Awaitable[bool]], retries: int = 2) -> bool:
    for attempt in range(1, retries + 2):
        try:
            ok = await action()
            if ok:
                return True
        except Exception as exc:  # noqa: BLE001
            if attempt >= retries + 1:
                raise RuntimeError(f"{step_name} failed after retries") from exc
        await asyncio.sleep(0.5 * attempt)
    return False


async def validate_required_fields(page: Page) -> tuple[bool, list[str]]:
    issues: list[str] = []
    required_fields = await page.query_selector_all("input[required], textarea[required], select[required]")
    for field in required_fields:
        try:
            tag = (await field.evaluate("el => el.tagName")).lower()
            val = ""
            if tag == "select":
                val = await field.evaluate("el => (el.value || '').toString()")
            else:
                val = await field.input_value()
            if not normalize_text(val):
                label = await field.get_attribute("aria-label") or await field.get_attribute("name") or "required-field"
                issues.append(f"Empty required field: {label}")
        except Exception:  # noqa: BLE001
            continue

    error_nodes = await page.query_selector_all(".error, [aria-invalid='true'], .invalid-feedback, .field-error")
    if error_nodes:
        issues.append(f"Validation errors visible: {len(error_nodes)}")

    return len(issues) == 0, issues


async def detect_submit_confirmation(
    page: Page,
    success_selectors: list[str],
    success_text_markers: list[str],
) -> bool:
    for selector in success_selectors:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            return True

    page_text = normalize_text(await page.content())
    for marker in success_text_markers:
        if normalize_text(marker) in page_text:
            return True
    return False


@dataclass
class ApplicationStateMachine:
    platform: str
    company: str
    title: str
    state: str = "created"
    history: list[str] = field(default_factory=list)

    def transition(self, new_state: str) -> None:
        self.state = new_state
        self.history.append(new_state)

    def summary(self) -> str:
        path = " -> ".join(self.history) if self.history else self.state
        return f"{self.platform} | {self.company} | {self.title} | {path}"
