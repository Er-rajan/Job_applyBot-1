"""Application tracker utilities."""

import csv
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
TRACKER_FILE = DATA_DIR / "applications.csv"
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


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def init_tracker():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TRACKER_FILE.exists():
        with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
        print(f"Tracker file created: {TRACKER_FILE}")


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
