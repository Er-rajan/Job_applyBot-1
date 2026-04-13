"""Best-effort handling for external application links."""

from __future__ import annotations

import asyncio

from playwright.async_api import Page


async def handle_external_link(
    base_page: Page,
    external_url: str,
    dry_run: bool = True,
    timeout_ms: int = 20000,
) -> tuple[bool, bool, str]:
    """
    Try to open an external job link and trigger an apply CTA if available.

    Returns: (handled, applied, message)
    """
    ext_page = await base_page.context.new_page()
    try:
        await ext_page.goto(external_url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001
        await ext_page.close()
        return False, False, f"open_failed: {type(exc).__name__}"

    selectors = [
        "button:has-text('Apply')",
        "button:has-text('Apply Now')",
        "button:has-text('Apply for this job')",
        "a:has-text('Apply')",
        "a:has-text('Apply Now')",
        "a:has-text('Apply on company site')",
        "input[type='submit'][value*='Apply']",
    ]

    apply_cta = None
    for selector in selectors:
        try:
            el = await ext_page.query_selector(selector)
            if el and await el.is_visible():
                apply_cta = el
                break
        except Exception:  # noqa: BLE001
            continue

    if not apply_cta:
        await ext_page.close()
        return True, False, "apply_cta_not_found"

    if dry_run:
        await ext_page.close()
        return True, False, "dry_run_apply_cta_found"

    try:
        await apply_cta.click()
        await asyncio.sleep(2)
        await ext_page.close()
        return True, True, "apply_cta_clicked"
    except Exception as exc:  # noqa: BLE001
        await ext_page.close()
        return True, False, f"apply_click_failed: {type(exc).__name__}"
