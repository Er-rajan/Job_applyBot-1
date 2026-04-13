"""Browser reliability helpers for Playwright bots."""

import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from playwright.async_api import Page

BASE_DIR = Path(__file__).resolve().parents[1]
FAILURE_DIR = BASE_DIR / "data" / "failures"


async def retry(coro_factory, attempts: int = 3, delay: float = 1.0):
    """Retry an async operation a few times before failing."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == attempts:
                raise
            await asyncio.sleep(delay)
    raise last_error


async def first_visible(page: Page, selectors: Iterable[str]):
    """Return first visible element matching any selector."""
    for selector in selectors:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            return el
    return None


async def safe_goto(page: Page, url: str, attempts: int = 3):
    return await retry(lambda: page.goto(url, wait_until="domcontentloaded"), attempts=attempts)


async def safe_fill(page: Page, selectors: Iterable[str], value: str, attempts: int = 3) -> bool:
    async def _do_fill():
        el = await first_visible(page, selectors)
        if not el:
            return False
        await el.fill(value)
        return True

    return await retry(_do_fill, attempts=attempts)


async def safe_click(page: Page, selectors: Iterable[str], attempts: int = 3) -> bool:
    async def _do_click():
        el = await first_visible(page, selectors)
        if not el:
            return False
        await el.click()
        return True

    return await retry(_do_click, attempts=attempts)


async def human_pause(base_delay: float, jitter_min: float = 0.6, jitter_max: float = 2.0):
    """Sleep with random jitter to avoid very fast repetitive actions."""
    low = max(0.0, min(jitter_min, jitter_max))
    high = max(jitter_min, jitter_max)
    await asyncio.sleep(max(0.0, base_delay) + random.uniform(low, high))


def _sanitize(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")[:80]


async def capture_failure(page: Optional[Page], platform: str, step: str, error: Exception):
    """Save failure details and screenshot for debugging."""
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    platform_part = _sanitize(platform)
    step_part = _sanitize(step)

    txt_path = FAILURE_DIR / f"{timestamp}_{platform_part}_{step_part}.txt"
    screenshot_path = FAILURE_DIR / f"{timestamp}_{platform_part}_{step_part}.png"

    details = [
        f"time: {datetime.now().isoformat()}",
        f"platform: {platform}",
        f"step: {step}",
        f"error: {type(error).__name__}: {error}",
    ]

    if page is not None:
        try:
            details.append(f"url: {page.url}")
        except Exception:  # noqa: BLE001
            pass

    txt_path.write_text("\n".join(details) + "\n", encoding="utf-8")

    if page is not None:
        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:  # noqa: BLE001
            pass

    return txt_path
