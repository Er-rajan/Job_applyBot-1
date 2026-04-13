"""Application tracker utilities."""

import csv
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
TRACKER_FILE = DATA_DIR / "applications.csv"
EXTERNAL_LINKS_FILE = DATA_DIR / "external_job_links.csv"
HEADERS = [
    "Date",
    "Time",
    "Platform",
    "Company",
    "Job Title",
    "Location",
    "Salary",
    "Status",
    "Job URL",
    "Notes",
]
EXTERNAL_HEADERS = [
    "Date",
    "Time",
    "Platform",
    "Company",
    "Job Title",
    "Job URL",
    "External URL",
    "Handled",
    "Applied",
    "Notes",
]


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def init_tracker():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TRACKER_FILE.exists():
        with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
        print(f"Tracker file created: {TRACKER_FILE}")
    if not EXTERNAL_LINKS_FILE.exists():
        with open(EXTERNAL_LINKS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(EXTERNAL_HEADERS)
        print(f"External links file created: {EXTERNAL_LINKS_FILE}")
    else:
        with open(EXTERNAL_LINKS_FILE, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        current_headers = [h.strip() for h in first_line.split(",")] if first_line else []
        if current_headers != EXTERNAL_HEADERS:
            _migrate_external_links_file()


def _migrate_external_links_file():
    rows: list[dict] = []
    with open(EXTERNAL_LINKS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    with open(EXTERNAL_LINKS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(EXTERNAL_HEADERS)
        for row in rows:
            writer.writerow(
                [
                    row.get("Date", ""),
                    row.get("Time", ""),
                    row.get("Platform", ""),
                    row.get("Company", ""),
                    row.get("Job Title", ""),
                    row.get("Job URL", ""),
                    row.get("External URL", ""),
                    row.get("Handled", ""),
                    row.get("Applied", ""),
                    row.get("Notes", ""),
                ]
            )


def is_duplicate_application(platform: str, company: str, job_title: str, job_url: str = "") -> bool:
    """Check if same job was already attempted before."""
    init_tracker()
    platform_n = _norm(platform)
    company_n = _norm(company)
    title_n = _norm(job_title)
    url_n = _norm(job_url)

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if _norm(row.get("Platform", "")) != platform_n:
                continue
            if url_n and _norm(row.get("Job URL", "")) == url_n:
                return True
            if _norm(row.get("Company", "")) == company_n and _norm(row.get("Job Title", "")) == title_n:
                return True
    return False


def log_application(
    platform,
    company,
    job_title,
    location="",
    salary="",
    status="Applied",
    job_url="",
    notes="",
):
    init_tracker()
    now = datetime.now()
    row = [
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        platform,
        company,
        job_title,
        location,
        salary,
        status,
        job_url,
        notes,
    ]
    with open(TRACKER_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)
    print(f"Logged: {company} - {job_title} [{platform}] - {status}")


def get_stats():
    init_tracker()
    total = 0
    today_count = 0
    platform_counts = {}
    today = datetime.now().strftime("%Y-%m-%d")

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if row["Date"] == today:
                today_count += 1
            p = row["Platform"]
            platform_counts[p] = platform_counts.get(p, 0) + 1

    print("\nApplication stats:")
    print(f"  Total applications: {total}")
    print(f"  Applications today: {today_count}")
    print("  Platform-wise:")
    for p, c in platform_counts.items():
        print(f"    {p}: {c}")
    print()
    return {"total": total, "today": today_count, "by_platform": platform_counts}


def update_status(job_url, new_status, notes=""):
    init_tracker()
    rows = []
    updated = False

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Job URL"] == job_url:
                row["Status"] = new_status
                row["Notes"] = notes
                updated = True
            rows.append(row)

    if updated:
        with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Status updated: {new_status}")
    else:
        print(f"URL not found: {job_url}")


def log_external_link(
    platform: str,
    company: str,
    job_title: str,
    job_url: str,
    external_url: str,
    handled: bool | None = None,
    applied: bool | None = None,
    notes: str = "",
):
    init_tracker()
    now = datetime.now()
    row = [
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        platform,
        company,
        job_title,
        job_url,
        external_url,
        str(handled).lower() if handled is not None else "",
        str(applied).lower() if applied is not None else "",
        notes,
    ]
    with open(EXTERNAL_LINKS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)
    print(f"External link logged: {external_url}")
