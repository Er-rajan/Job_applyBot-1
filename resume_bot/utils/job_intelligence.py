"""Job requirement matching and external-link detection helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from playwright.async_api import Page


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _host(url: str) -> str:
    try:
        return _norm(urlparse(url).netloc)
    except Exception:  # noqa: BLE001
        return ""


async def extract_job_text(page: Page) -> str:
    try:
        body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        return _norm(body_text)
    except Exception:  # noqa: BLE001
        return ""


def keyword_match(job_text: str, keywords: list[str], min_matches: int = 1) -> tuple[bool, list[str]]:
    normalized = _norm(job_text)
    found: list[str] = []
    for keyword in keywords:
        key = _norm(keyword)
        if key and key in normalized:
            found.append(keyword)
    unique_found = sorted(set(found), key=lambda s: s.lower())
    return len(unique_found) >= max(1, int(min_matches)), unique_found


async def find_external_links(page: Page, platform_domains: list[str]) -> list[str]:
    platform_hosts = {_norm(domain) for domain in platform_domains if domain}
    links = await page.query_selector_all("a[href]")
    external: list[str] = []

    for link in links:
        href = await link.get_attribute("href")
        if not href or not href.startswith("http"):
            continue

        host = _host(href)
        if not host:
            continue

        if any(host == d or host.endswith(f".{d}") for d in platform_hosts):
            continue
        external.append(href.strip())

    return sorted(set(external))
