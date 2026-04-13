# Resume Bot

Apply jobs on Naukri, Indeed, Internshala, and Apna using Playwright.
This version includes retries, duplicate prevention, dry-run mode, and failure snapshots.

## Setup

```bash
cd resume_bot
pip install -r requirements.txt
playwright install chromium
```

## Configure

Edit `config.py` and set:
- your credentials for each enabled platform
- target job titles and locations
- resume path (`data/my_resume.pdf` by default)
- `headless=False` for first-time debugging
- `application_profile` values like `cgpa`, `college`, `tenth_percentage`, `twelfth_percentage`, `source`, and `location` for form auto-fill

Place your resume at:
- `resume_bot/data/my_resume.pdf`

## Run

```bash
# Single platform test
python3 main.py --platform naukri --force

# Dry run (logs matches, does not apply)
python3 main.py --platform naukri --dry-run --force

# Run all enabled platforms
python3 main.py --force

# Show stats
python3 main.py --stats
```

## Daily Schedule (cron)

```bash
chmod +x setup_cron.sh
./setup_cron.sh

# verify
crontab -l
```

## Output Files

- `data/applications.csv`: application tracking
- `data/bot_log.txt`: run logs
- `data/failures/*.txt`: failure details (step + error)
- `data/failures/*.png`: failure screenshots

## Notes

- Use valid credentials in `config.py`
- Apna login requires OTP input
- Application forms with common questions (CGPA/college/10th-12th/source/location/etc.) are auto-filled from `application_profile`
- Duplicate jobs are skipped using `applications.csv` (URL or company+title+platform)
ok
