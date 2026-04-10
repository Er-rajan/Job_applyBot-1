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

CRON_JOB="0 18 * * * cd $BOT_DIR && $PYTHON_PATH $MAIN_FILE --force >> $LOG_FILE 2>&1"

(crontab -l 2>/dev/null | grep -q "$MAIN_FILE") && {
    echo "Cron job already exists. Use crontab -e to update if needed."
} || {
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added for 18:00 daily."
}

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
