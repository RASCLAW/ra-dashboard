"""
Rasclaw Bot -- RA's personal Telegram command center.

Listens for messages, executes commands, sends results.
No Claude needed -- direct command handlers for speed.

Commands:
    status / check    -- system health check
    brief             -- send pre-shift brief
    tunnel / start    -- start VSCode remote tunnel
    belle             -- check/restart Belle bot
    scout             -- trigger job scout
    dash              -- dashboard freshness check
    help              -- list commands

Usage:
    python rasclaw_bot.py              # Run polling loop
    python rasclaw_bot.py --once       # Process one batch and exit
"""

import os
import sys
import json
import time
import subprocess
import signal
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from send_message import send_to_ra, ENV

PHT = timezone(timedelta(hours=8))
BOT_TOKEN = ENV.get("RASCLAW_TG_BOT_TOKEN")
CHAT_ID = ENV.get("RASCLAW_TG_CHAT_ID")
PYTHON = "/home/ra/projects/DuberyMNL/.venv/bin/python"
DASHBOARD_DB = Path("/home/ra/projects/ra-dashboard/dashboard-db.json")
LOG_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/rasclaw_bot.log")
CONVO_LOG = Path("/home/ra/projects/ra-dashboard/.tmp/rasclaw_conversations.log")
OFFSET_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/rasclaw_bot_offset")
LOCK_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/rasclaw_bot.lock")
POLL_INTERVAL = 2

running = True
def handle_signal(sig, frame):
    global running
    print("\nShutting down...")
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def acquire_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            print(f"Already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))


def release_lock():
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except:
            pass


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_convo(sender, text):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    CONVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CONVO_LOG, "a") as f:
        f.write(f"[{ts}] {sender}: {text}\n")


def get_offset():
    if OFFSET_FILE.exists():
        return int(OFFSET_FILE.read_text().strip())
    return 0


def save_offset(offset):
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def poll_updates():
    offset = get_offset()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset + 1
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])
        return []
    except Exception as e:
        log(f"Poll error: {e}")
        return []


def check_process(pattern):
    try:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        return False


def check_cron(pattern):
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        return pattern in result.stdout
    except:
        return False


# === COMMAND HANDLERS ===

def cmd_status():
    """Full system health check."""
    systems = [
        ("Remote Tunnel", check_process("code-tunnel") or check_process("code-server")),
        ("Tunnel Watchdog", Path("/home/ra/.vscode/cli/tunnel-stable.lock").exists()),
        ("Belle Bot", check_process("arabelle_bot.py")),
        ("Rasclaw Bot", True),  # we're running
        ("Dashboard Cron", check_cron("dashboard_sync.py")),
        ("Belle Watchdog", check_cron("belle_watchdog")),
    ]

    lines = ["\U0001f50d <b>System Status</b>", ""]
    all_good = True
    for name, ok in systems:
        if ok:
            lines.append(f"\u2705 {name}")
        else:
            lines.append(f"\u274c {name} -- <b>DOWN</b>")
            all_good = False

    if all_good:
        lines.append(f"\nAll clear.")
    else:
        lines.append(f"\nFix the items above.")

    return "\n".join(lines)


def cmd_tunnel():
    """Start VSCode remote tunnel."""
    if check_process("code-tunnel"):
        return "\u2705 Tunnel is already running."

    try:
        subprocess.Popen(
            ["nohup", "code-tunnel", "tunnel", "--name", "dubery-dev", "--accept-server-license-terms"],
            stdout=open("/tmp/tunnel.log", "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        time.sleep(3)
        if check_process("code-tunnel"):
            return "\u2705 Tunnel started. Connect via vscode.dev > dubery-dev"
        else:
            return "\u26a0\ufe0f Tunnel command sent but process not detected yet. Check in a minute."
    except Exception as e:
        return f"\u274c Failed to start tunnel: {e}"


def cmd_belle():
    """Check Belle bot, restart if down."""
    if check_process("arabelle_bot.py"):
        return "\u2705 Belle is running."

    try:
        subprocess.Popen(
            [PYTHON, "/home/ra/projects/ra-dashboard/tools/telegram/arabelle_bot.py"],
            stdout=open("/home/ra/projects/ra-dashboard/.tmp/arabelle_bot.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd="/home/ra/projects/ra-dashboard"
        )
        time.sleep(3)
        if check_process("arabelle_bot.py"):
            return "\u2705 Belle was down. Restarted."
        else:
            return "\u26a0\ufe0f Restart sent but Belle not detected yet."
    except Exception as e:
        return f"\u274c Failed to restart Belle: {e}"


def cmd_brief():
    """Send pre-shift brief."""
    try:
        result = subprocess.run(
            [PYTHON, "/home/ra/projects/ra-dashboard/tools/telegram/ra_preshift_brief.py"],
            capture_output=True, text=True, timeout=30,
            cwd="/home/ra/projects/ra-dashboard"
        )
        if result.returncode == 0:
            return None  # Brief sends itself, no extra reply needed
        else:
            return f"\u274c Brief failed: {result.stderr[:200]}"
    except Exception as e:
        return f"\u274c Brief error: {e}"


def cmd_dash():
    """Dashboard freshness check."""
    if not DASHBOARD_DB.exists():
        return "\u274c Dashboard DB not found."

    db = json.loads(DASHBOARD_DB.read_text())
    now = datetime.now(PHT)

    def hrs_since(date_str, time_str=None):
        if not date_str:
            return float('inf')
        t = (time_str or '12:00').strip()[:5]
        try:
            dt = datetime.fromisoformat(f"{date_str}T{t}:00+08:00")
            return (now - dt).total_seconds() / 3600
        except:
            return float('inf')

    lines = ["\U0001f4ca <b>Dashboard Check</b>", ""]

    # Last updated
    lu = db.get('last_updated', '')
    if lu:
        h = hrs_since(lu[:10], lu[11:16] if len(lu) > 11 else None)
        lines.append(f"Updated {h:.0f}h ago" if h >= 1 else f"Updated {int(h*60)}m ago")

    # Baby Jah
    jah = db.get('shared', {}).get('baby_jah', {})
    feeds = jah.get('feeding', [])
    if feeds:
        lf = feeds[-1]
        fh = hrs_since(lf.get('date'), lf.get('time'))
        icon = "\U0001f6a8" if fh > 8 else "\U0001f37c"
        lines.append(f"{icon} Jah fed {fh:.0f}h ago ({lf.get('food','')})")

    diapers = jah.get('diapers', [])
    if diapers:
        ld = diapers[-1]
        dh = hrs_since(ld.get('date'), ld.get('time'))
        if dh > 6:
            lines.append(f"\u26a0\ufe0f Diaper {dh:.0f}h ago")

    sleeps = jah.get('sleep', [])
    active = None
    for s in reversed(sleeps):
        if s.get('slept') and not s.get('woke'):
            active = s
            break
    if active:
        sh = hrs_since(active['date'], active['slept'])
        lines.append(f"\U0001f634 Sleeping for {sh:.1f}h")

    # Accounts
    accts = db.get('shared', {}).get('accounts', {})
    total = sum(accts.get(a, {}).get('balance', 0) for a in ['payroll', 'savings', 'pocket_cash'])
    lines.append(f"\n\U0001f4b0 P{total:,.0f} total")

    return "\n".join(lines)


def cmd_scout():
    """Trigger job scout."""
    scout_path = Path("/home/ra/projects/DuberyMNL/tools/upwork/scout.py")
    if not scout_path.exists():
        return "\u274c scout.py not found."

    try:
        result = subprocess.run(
            [PYTHON, str(scout_path), "--telegram"],
            capture_output=True, text=True, timeout=120,
            cwd="/home/ra/projects/DuberyMNL"
        )
        if result.returncode == 0:
            return "\u2705 Job scout complete. Results sent."
        else:
            return f"\u26a0\ufe0f Scout finished with issues:\n{result.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return "\u26a0\ufe0f Scout timed out (2 min limit)."
    except Exception as e:
        return f"\u274c Scout error: {e}"


def cmd_help():
    """List available commands."""
    return (
        "\U0001f916 <b>Rasclaw Commands</b>\n\n"
        "<b>status</b> -- system health check\n"
        "<b>tunnel</b> -- start VSCode tunnel\n"
        "<b>belle</b> -- check/restart Belle bot\n"
        "<b>brief</b> -- send pre-shift brief\n"
        "<b>dash</b> -- dashboard freshness\n"
        "<b>scout</b> -- run job scout\n"
        "<b>help</b> -- this message"
    )


NOTES_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/rasclaw_notes.log")

def cmd_note(text):
    """Save a quick note/log from RA."""
    # Strip the trigger word
    for prefix in ['log ', 'note ', 'remember ', 'save ']:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    if not text.strip():
        return "What do you want me to note down?"
    ts = datetime.now(PHT).strftime("%Y-%m-%d %I:%M %p")
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTES_FILE, "a") as f:
        f.write(f"[{ts}] {text.strip()}\n")
    return f"\u270f\ufe0f Noted: <i>{text.strip()}</i>"


# Command routing
COMMANDS = {
    'status': cmd_status, 'check': cmd_status, 'sys': cmd_status,
    'tunnel': cmd_tunnel, 'start': cmd_tunnel,
    'belle': cmd_belle,
    'brief': cmd_brief, 'preshift': cmd_brief,
    'dash': cmd_dash, 'dashboard': cmd_dash, 'fresh': cmd_dash,
    'scout': cmd_scout, 'jobs': cmd_scout,
    'help': cmd_help, '?': cmd_help,
}

# Prefix commands (checked before single-word commands)
NOTE_TRIGGERS = ['log ', 'note ', 'remember ', 'save ']


def get_dashboard_snapshot():
    """Get concise dashboard state for Claude context."""
    if not DASHBOARD_DB.exists():
        return "{}"
    db = json.loads(DASHBOARD_DB.read_text())
    now = datetime.now(PHT)
    snapshot = {
        "time": now.strftime("%Y-%m-%d %I:%M %p PHT"),
        "accounts": db.get("shared", {}).get("accounts", {}),
        "bills": [b for b in db.get("shared", {}).get("bills", {}).get("items", []) if b.get("status") != "paid"],
        "baby_jah_feeding": (db.get("shared", {}).get("baby_jah", {}).get("feeding", []) or [])[-3:],
        "baby_jah_sleep": (db.get("shared", {}).get("baby_jah", {}).get("sleep", []) or [])[-2:],
        "ra_todos": [t for t in db.get("ra", {}).get("todos", []) if not t.get("done")],
        "ra_projects": db.get("ra", {}).get("builder", {}).get("projects", [])[:5],
        "location": db.get("location", {}),
    }
    return json.dumps(snapshot, default=str)


def get_recent_convo(limit=10):
    """Get last N conversation lines for context."""
    if not CONVO_LOG.exists():
        return ""
    lines = CONVO_LOG.read_text().strip().split("\n")
    return "\n".join(lines[-limit:])


SKILL_PATH = Path("/home/ra/.claude/skills/rasclaw-agent/SKILL.md")

def chat_with_claude(message):
    """Send message to Claude via --print for conversational response."""
    skill = SKILL_PATH.read_text() if SKILL_PATH.exists() else ""
    snapshot = get_dashboard_snapshot()
    recent = get_recent_convo()

    prompt = f"""{skill}

## Dashboard Snapshot
{snapshot}

## Recent Conversation
{recent}

## RA's Message
{message}

Respond as Rasclaw. Keep it short. Use HTML formatting for Telegram (<b>bold</b>, <i>italic</i>). No markdown."""

    try:
        log(f"Calling Claude Opus...")
        result = subprocess.run(
            ["claude", "--print", "--model", "opus"],
            input=prompt,
            capture_output=True, text=True, timeout=60
        )
        log(f"Claude returned: rc={result.returncode} stdout={len(result.stdout)}chars stderr={result.stderr[:100]}")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            log(f"Claude error: {result.stderr[:300]}")
            return "Couldn't process that. Try a command -- type <b>help</b>."
    except subprocess.TimeoutExpired:
        log("Claude timed out (60s)")
        return "Took too long. Try again or use a command."
    except Exception as e:
        log(f"Claude failed: {e}")
        return "Something broke. Try a command -- type <b>help</b>."


def process_message(text):
    """Route: notes -> commands -> Claude conversation."""
    lower = text.strip().lower()

    # Check note triggers first (multi-word prefix)
    for trigger in NOTE_TRIGGERS:
        if lower.startswith(trigger):
            log(f"Note: {text[:50]}")
            return cmd_note(text.strip())

    # Single-word commands
    cmd = lower.split()[0] if lower else ''
    handler = COMMANDS.get(cmd)
    if handler:
        log(f"Command: {cmd}")
        return handler()

    # Everything else -> Claude conversation
    log(f"Chat: {text[:50]}")
    return chat_with_claude(text)


def main():
    acquire_lock()
    log("Rasclaw bot started.")

    try:
        while running:
            updates = poll_updates()
            for update in updates:
                save_offset(update["update_id"])
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Only respond to RA
                if chat_id != CHAT_ID:
                    continue

                if not text:
                    continue

                log_convo("RA", text)
                reply = process_message(text)
                if reply:
                    send_to_ra(reply)
                    log_convo("Rasclaw", reply[:100])

            time.sleep(POLL_INTERVAL)

    except Exception as e:
        log(f"Fatal error: {e}")
    finally:
        release_lock()
        log("Rasclaw bot stopped.")


if __name__ == "__main__":
    if "--once" in sys.argv:
        acquire_lock()
        updates = poll_updates()
        for update in updates:
            save_offset(update["update_id"])
            msg = update.get("message", {})
            text = msg.get("text", "")
            if text:
                reply = process_message(text)
                if reply:
                    send_to_ra(reply)
        release_lock()
    else:
        main()
