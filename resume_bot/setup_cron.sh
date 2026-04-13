#!/bin/bash

set -e

echo "Resume Bot scheduler setup"
echo "=========================="

PYTHON_PATH=$(which python3)
echo "Python: $PYTHON_PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_DIR="$SCRIPT_DIR"
MAIN_FILE="$BOT_DIR/main.py"
LOG_FILE="$BOT_DIR/data/bot_log.txt"

mkdir -p "$BOT_DIR/data"

CRON_JOB="0 8-22/2 * * * cd $BOT_DIR && $PYTHON_PATH $MAIN_FILE --force >> $LOG_FILE 2>&1"

# Replace older bot schedule entries and keep all other cron jobs.
EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
UPDATED_CRON="$(printf '%s\n' "$EXISTING_CRON" | grep -v "$MAIN_FILE" || true)"
{
    printf "%s\n" "$UPDATED_CRON"
    echo "$CRON_JOB"
} | sed '/^$/N;/^\n$/D' | crontab -
echo "Cron job set: every 2 hours from 08:00 to 22:00."

echo
echo "Current cron jobs:"
crontab -l

echo
echo "Useful commands:"
echo "  View cron:   crontab -l"
echo "  Edit cron:   crontab -e"
echo "  Remove cron: crontab -r"
echo "  View logs:   tail -f $LOG_FILE"
echo "  Run now:     cd $BOT_DIR && python3 main.py --force"
