#!/bin/bash
# Belle Bot Watchdog
# Checks if arabelle_bot.py is running. If not, restarts it.
# Run via cron every 5 minutes.
#
# Cron entry:
# */5 * * * * /home/ra/projects/ra-dashboard/tools/telegram/belle_watchdog.sh >> /home/ra/projects/ra-dashboard/.tmp/belle_watchdog.log 2>&1

PYTHON="/home/ra/projects/DuberyMNL/.venv/bin/python"
BOT_SCRIPT="/home/ra/projects/ra-dashboard/tools/telegram/arabelle_bot.py"
LOCK_FILE="/home/ra/projects/ra-dashboard/.tmp/arabelle_bot.lock"
LOG="/home/ra/projects/ra-dashboard/.tmp/belle_watchdog.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Check if bot process is running
if pgrep -f "arabelle_bot.py" > /dev/null 2>&1; then
    # Running -- check if it's actually healthy (not stuck in timeout loop)
    BOT_PID=$(pgrep -f "arabelle_bot.py" | head -1)

    # Check if the bot log has only timeout errors in the last 20 lines
    RECENT_ERRORS=$(tail -20 /home/ra/projects/ra-dashboard/.tmp/arabelle_bot.log 2>/dev/null | grep -c "timed out\|error\|Error")
    RECENT_LINES=$(tail -20 /home/ra/projects/ra-dashboard/.tmp/arabelle_bot.log 2>/dev/null | wc -l)

    if [ "$RECENT_ERRORS" -ge 18 ] && [ "$RECENT_LINES" -ge 20 ]; then
        echo "[$TIMESTAMP] Bot stuck in error loop (${RECENT_ERRORS}/${RECENT_LINES} errors). Killing and restarting..."
        pkill -f "arabelle_bot.py"
        sleep 2
        rm -f "$LOCK_FILE"
        cd /home/ra/projects/ra-dashboard && nohup $PYTHON $BOT_SCRIPT >> /home/ra/projects/ra-dashboard/.tmp/arabelle_bot.log 2>&1 &
        echo "[$TIMESTAMP] Restarted (PID: $!)"
    fi
else
    # Not running -- start it
    echo "[$TIMESTAMP] Bot not running. Starting..."
    rm -f "$LOCK_FILE"
    cd /home/ra/projects/ra-dashboard && nohup $PYTHON $BOT_SCRIPT >> /home/ra/projects/ra-dashboard/.tmp/arabelle_bot.log 2>&1 &
    echo "[$TIMESTAMP] Started (PID: $!)"
fi
