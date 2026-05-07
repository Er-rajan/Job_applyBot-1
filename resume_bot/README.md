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
- browser settings (`browser.engine`, `browser.channel`, `browser.executable_path`)
- `headless=False` for first-time debugging
- `application_profile` values like `cgpa`, `college`, `tenth_percentage`, `twelfth_percentage`, `source`, and `location` for form auto-fill
- `requirement_keywords` and `min_keyword_matches` for requirement-based apply filtering
- `max_external_links_per_job` to control how many external apply links are handled per job

Place your resume at:
- `resume_bot/data/my_resume.pdf`

Browser examples in `config.py`:
- Chrome: `engine="chromium"`, `channel="chrome"`, `executable_path=""`
- Edge: `engine="chromium"`, `channel="msedge"`, `executable_path=""`
- Brave: `engine="chromium"`, `channel=""`, `executable_path="/usr/bin/brave-browser"`

## Run

```bash
# Single platform test
python3 main.py --platform naukri --force

# Dry run (logs matches, does not apply)
python3 main.py --platform naukri --dry-run --force

# Validation run (opens application flow, validates fields, no final submit)
python3 main.py --platform naukri --validate-run --force

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
- `data/external_job_links.csv`: external company apply links + handling status (`Handled`, `Applied`)
- `data/bot_log.txt`: run logs
- `data/application_question_bank.json`: reusable question-answer bank across portals
- `data/failures/*.txt`: failure details (step + error)
- `data/failures/*.png`: failure screenshots

## Notes

- Use valid credentials in `config.py`
- Apna login requires OTP input
- Application forms with common questions (CGPA/college/10th-12th/source/location/etc.) are auto-filled from `application_profile`
- Unknown form questions are saved with `TODO_ANSWER` in `data/application_question_bank.json` so you can fill once and reuse forever
- You can pre-add common portal questions in `data/application_question_bank.json` and manually set answers (`TODO_ANSWER` -> your final answer)
- Accuracy guardrails now include popup handling, required-field checks, question fuzzy-matching, retryable steps, and post-submit confirmation checks
- Each apply attempt now tracks stage flow in tracker notes (`opened -> apply-clicked -> questions-filled -> applied/submitted`)
- Configure accuracy controls in `config.py` via `accuracy` and `platform_selectors`
- Jobs are skipped if requirement keywords do not match (based on `requirement_keywords`)
- External company application links are handled in best-effort mode and logged with `Handled`/`Applied` true-false status
- Duplicate jobs are skipped using `applications.csv` (URL or company+title+platform)
ok



cd /home/rajan/Downloads/resume_bot_v2/resume_bot

First test (safe):
python3 main.py --dry-run --force

Real apply:
python3 main.py --force

Single platform:
python3 main.py --platform indeed --force

How many times:

One manual run = one full session (then stops).
Your cron is already set to run 8 times/day:
08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00
Per run, max applies are controlled by max_applications_per_day in config.py (currently 20).
 helo ni 