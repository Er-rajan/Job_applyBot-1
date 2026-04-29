"""Resume Bot main runner."""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from config import CONFIG
from platforms.indeed_apna_bot import ApnaBot, IndeedBot
from platforms.internshala_bot import InternshalaBot
from platforms.naukri_bot import NaukriBot
from utils.browser_utils import capture_failure
from utils.tracker import get_stats, init_tracker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = DATA_DIR / "bot_log.txt"
os.makedirs(DATA_DIR, exist_ok=True)


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def already_ran_today() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    if not LOG_FILE.exists():
        return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if today in line and "RUN COMPLETE" in line:
                return True
    return False


def resolve_resume_path() -> Path:
    resume_path = Path(CONFIG.get("resume_path", "data/my_resume.pdf"))
    if resume_path.is_absolute():
        return resume_path
    return BASE_DIR / resume_path


def resolve_browser_settings(config: dict) -> tuple[str, dict]:
    browser_cfg = config.get("browser", {})
    engine = str(browser_cfg.get("engine", "chromium")).strip().lower()
    if engine not in {"chromium", "firefox", "webkit"}:
        engine = "chromium"

    launch_options = {"headless": bool(config.get("headless", False))}
    if engine == "chromium":
        launch_options["args"] = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]

        executable_path = str(browser_cfg.get("executable_path", "")).strip()
        channel = str(browser_cfg.get("channel", "")).strip().lower()

        # Prefer executable_path when user wants a custom Chromium browser like Brave.
        if executable_path:
            launch_options["executable_path"] = executable_path
        elif channel:
            launch_options["channel"] = channel

    return engine, launch_options


async def run_bots(platforms: list[str] | None = None, dry_run: bool = False, validate_run: bool = False):
    init_tracker()
    log("RESUME BOT START")
    log(f"Start time: {datetime.now().strftime('%A, %d %B %Y - %I:%M %p')}")
    log(f"Dry run mode: {'ON' if dry_run else 'OFF'}")
    log(f"Validate mode: {'ON' if validate_run else 'OFF'}")

    if platforms is None:
        platforms = ["naukri", "indeed", "internshala", "apna"]

    resume_file = resolve_resume_path()
    if not resume_file.exists():
        log(f"Warning: Resume file missing at {resume_file}")

    async with async_playwright() as playwright:
        engine, launch_options = resolve_browser_settings(CONFIG)
        log(f"Browser engine: {engine}")
        if launch_options.get("channel"):
            log(f"Browser channel: {launch_options['channel']}")
        if launch_options.get("executable_path"):
            log(f"Browser executable: {launch_options['executable_path']}")

        browser_launcher = getattr(playwright, engine)
        browser = await browser_launcher.launch(**launch_options)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        total_applied = 0
        portal_applied: dict[str, int] = {}
        run_order = [
            ("naukri", NaukriBot),
            ("indeed", IndeedBot),
            ("internshala", InternshalaBot),
            ("apna", ApnaBot),
        ]

        for name, bot_cls in run_order:
            if name not in platforms or not CONFIG["platforms"][name]["enabled"]:
                continue
            try:
                runtime_config = dict(CONFIG)
                runtime_config["dry_run"] = dry_run
                runtime_config["validate_mode"] = validate_run
                bot = bot_cls(runtime_config)
                await bot.run(page)
                total_applied += bot.applied_count
                portal_applied[name] = bot.applied_count
                log(f"{name.title()} successful applies: {bot.applied_count}")
            except Exception as exc:
                log(f"{name.title()} bot crashed: {exc}")
                await capture_failure(page, name.title(), "bot_run", exc)
                portal_applied[name] = 0

        await browser.close()

    for portal_name in ["naukri", "indeed", "internshala", "apna"]:
        if portal_name in portal_applied:
            log(f"SUMMARY {portal_name.title()}: {portal_applied[portal_name]} applied")
    log(f"RUN COMPLETE. Total applications sent: {total_applied}")
    get_stats()


def main():
    os.chdir(BASE_DIR)
    parser = argparse.ArgumentParser(description="Resume Apply Bot")
    parser.add_argument("--platform", choices=["naukri", "indeed", "internshala", "apna"])
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--force", action="store_true", help="Run even if already executed today")
    parser.add_argument("--dry-run", action="store_true", help="Collect and log jobs without applying")
    parser.add_argument(
        "--validate-run",
        action="store_true",
        help="Open application flows, validate fields and selectors, but avoid final submit",
    )
    args = parser.parse_args()

    if args.stats:
        get_stats()
        return

    if not args.force and already_ran_today():
        log("Already ran today. Use --force to run again.")
        sys.exit(0)

    if args.platform:
        asyncio.run(run_bots([args.platform], dry_run=args.dry_run, validate_run=args.validate_run))
    else:
        asyncio.run(run_bots(dry_run=args.dry_run, validate_run=args.validate_run))


if __name__ == "__main__":
    main()
