"""
Arabelle Bot -- Telegram polling loop + Claude-powered responses.

Polls for new messages from Arabelle, processes them through Claude
using the arabelle-agent skill, updates dashboard data, and responds.

Usage:
    python arabelle_bot.py              # Run polling loop (30s interval)
    python arabelle_bot.py --once       # Process one batch and exit
    python arabelle_bot.py --test "hi"  # Test with a fake message

Requires:
    - ARABELLE_TG_BOT_TOKEN and ARABELLE_TG_CHAT_ID in .env
    - claude CLI available in PATH
    - dashboard-db.json accessible
"""

import os
import sys
import json
import time
import subprocess
import signal
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from send_message import send_to_arabelle, ENV

# Paths
DASHBOARD_DB = Path("/home/ra/projects/ra-dashboard/dashboard-db.json")
SKILL_PATH = Path("/home/ra/.claude/skills/arabelle-agent/SKILL.md")
MEMORY_DIR = Path("/home/ra/.claude/projects/-home-ra-projects-ra-dashboard/memory")
PATTERNS_FILE = MEMORY_DIR / "arabelle_patterns.md"
BUILD_SCRIPT = Path("/home/ra/projects/ra-dashboard/tools/sync/build_dashboard.py")
PYTHON = "/home/ra/projects/DuberyMNL/.venv/bin/python"
LOG_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/arabelle_bot.log")
CONVO_LOG = Path("/home/ra/projects/ra-dashboard/.tmp/belle_conversations.log")

BOT_TOKEN = ENV.get("ARABELLE_TG_BOT_TOKEN")
POLL_INTERVAL = 2  # seconds between polls (keep short, long polling handles the wait)
OFFSET_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/arabelle_bot_offset")
LOCK_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/arabelle_bot.lock")

# Graceful shutdown
running = True
def handle_signal(sig, frame):
    global running
    print("\nShutting down gracefully...")
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def acquire_lock():
    """Ensure only one bot instance runs. Kill stale locks."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            # Check if process is still alive
            os.kill(old_pid, 0)
            print(f"ERROR: Another instance is running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Stale lock, remove it
            LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))


def release_lock():
    """Remove lock file on exit."""
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except:
            pass


def log(msg):
    """Log to file and stdout."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def log_conversation(sender, text):
    """Log conversation to belle_conversations.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    CONVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CONVO_LOG, "a") as f:
        f.write(f"[{ts}] {sender}: {text}\n")


def get_offset():
    """Get the last processed update_id."""
    if OFFSET_FILE.exists():
        return int(OFFSET_FILE.read_text().strip())
    return 0


def save_offset(offset):
    """Save the last processed update_id."""
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def poll_updates():
    """Poll Telegram for new messages."""
    import requests
    offset = get_offset()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}  # shorter timeout for unstable connections
    if offset:
        params["offset"] = offset + 1

    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])
        else:
            log(f"API error: {data}")
            return []
    except Exception as e:
        log(f"Poll error: {e}")
        return []


def get_dashboard_snapshot():
    """Get current dashboard state for Claude context."""
    if not DASHBOARD_DB.exists():
        return "{}"

    with open(DASHBOARD_DB) as f:
        db = json.load(f)

    # Extract relevant sections (keep it concise for Claude)
    snapshot = {
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M PHT"),
        "accounts": db.get("shared", {}).get("accounts", {}),
        "pending_bills": [
            b for b in db.get("shared", {}).get("bills", {}).get("items", [])
            if b.get("status") == "pending"
        ],
        "baby_jah": {
            "feedings": (db.get("shared", {}).get("baby_jah", {}).get("feedings", []) or [])[-3:],
            "diapers": (db.get("shared", {}).get("baby_jah", {}).get("diapers", []) or [])[-3:],
            "sleep": (db.get("shared", {}).get("baby_jah", {}).get("sleep", []) or [])[-2:],
        },
        "arabelle_todos": db.get("arabelle", {}).get("todos", []),
        "active_trip": None,
        "location": db.get("location", {}),
    }

    # Active trip
    trips = db.get("shared", {}).get("trips", [])
    active = [t for t in trips if t.get("status") == "active"]
    if active:
        trip = active[0]
        snapshot["active_trip"] = {
            "destination": trip.get("destination"),
            "dates": trip.get("dates"),
            "budget_total": trip.get("budget", {}).get("total"),
            "actual_spending": trip.get("actual_spending"),
        }

    return json.dumps(snapshot, indent=2, ensure_ascii=False)


def get_recent_conversation(limit=10):
    """Get last N conversation exchanges for context."""
    if not CONVO_LOG.exists():
        return ""
    lines = CONVO_LOG.read_text().strip().splitlines()
    recent = lines[-limit:] if len(lines) > limit else lines
    if not recent:
        return ""
    return "\n".join(recent)


def build_prompt(message_text):
    """Build the full prompt for Claude."""
    skill_content = SKILL_PATH.read_text() if SKILL_PATH.exists() else ""
    dashboard_state = get_dashboard_snapshot()
    recent_convo = get_recent_conversation()

    prompt = f"""You are Ara-bot (Belle). Follow the instructions in the skill below.

--- SKILL ---
{skill_content}
--- END SKILL ---

--- CURRENT DASHBOARD STATE ---
{dashboard_state}
--- END STATE ---

--- RECENT CONVERSATION ---
{recent_convo if recent_convo else "(no prior messages)"}
--- END CONVERSATION ---

--- ARABELLE'S NEW MESSAGE ---
{message_text}
--- END MESSAGE ---

IMPORTANT RULES:
- Be time-aware. The current time is in the dashboard state. Adjust your tone: late night (10PM-5AM) = "you're still up?", early morning (5-8AM) = "good morning!", afternoon = casual. Never say "good morning" at night.
- Be conversational. Talk like a friend, not a robot. No bullet points, no structured lists.
- Keep replies to 1-3 short sentences max. Match her energy -- short message = short reply.
- Pure casual English. Only use Tagalog if she does first.
- If she says a single word like "food", "budget", "schedule" -- just answer it naturally, don't ask for clarification.
- Never start with "Sure!" or "Of course!" or "Great question!" -- just answer directly.
- Use the dashboard state to give real numbers and data when relevant.
- You CAN include URLs in your replies. Telegram will auto-embed YouTube videos with thumbnails. If she asks for a recipe video or any link, include a real YouTube search URL like https://www.youtube.com/results?search_query=sardine+omelette+recipe or a direct video link if you know one. Never say you can't send links -- you can.

If the message requires logging data, include an ACTION block at the END (after your reply), formatted exactly as:
```action
{{"action": "log|read|create_event|add_todo", "target": "baby_jah.feedings|baby_jah.diapers|arabelle.transactions|etc", "data": {{...}}}}
```

If you notice a pattern worth remembering, include an OBSERVATION block:
```observation
{{"type": "pattern|preference|routine_change|health_engagement", "detail": "...", "action": "..."}}
```

Reply text comes FIRST, action/observation blocks come LAST."""

    return prompt


def call_claude(prompt):
    """Call claude --print with the prompt."""
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "opus", prompt],
            capture_output=True,
            text=True,
            timeout=60,
            cwd="/home/ra/projects/ra-dashboard"
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            log(f"Claude error: {result.stderr[:200]}")
            return None
    except subprocess.TimeoutExpired:
        log("Claude timed out (60s)")
        return None
    except FileNotFoundError:
        log("Claude CLI not found in PATH")
        return None
    except Exception as e:
        log(f"Claude call failed: {e}")
        return None


def parse_response(response):
    """Parse Claude's response into reply text and action blocks."""
    reply = response
    actions = []
    observations = []

    # Extract action blocks
    if "```action" in response:
        parts = response.split("```action")
        reply = parts[0].strip()
        for part in parts[1:]:
            json_str = part.split("```")[0].strip()
            try:
                actions.append(json.loads(json_str))
            except json.JSONDecodeError:
                log(f"Failed to parse action: {json_str[:100]}")

    # Extract observation blocks
    if "```observation" in reply:
        parts = reply.split("```observation")
        reply = parts[0].strip()
        for part in parts[1:]:
            json_str = part.split("```")[0].strip()
            try:
                observations.append(json.loads(json_str))
            except json.JSONDecodeError:
                log(f"Failed to parse observation: {json_str[:100]}")

    return reply, actions, observations


def execute_actions(actions):
    """Execute data actions on dashboard-db.json."""
    if not actions:
        return

    with open(DASHBOARD_DB) as f:
        db = json.load(f)

    for action in actions:
        act_type = action.get("action")
        target = action.get("target", "")
        data = action.get("data", {})

        try:
            if act_type == "log":
                # Navigate to the target array and append
                parts = target.split(".")
                obj = db
                for part in parts[:-1]:
                    obj = obj.setdefault(part, {})
                arr_key = parts[-1]
                if arr_key not in obj:
                    obj[arr_key] = []
                if isinstance(obj[arr_key], list):
                    obj[arr_key].append(data)
                    log(f"Logged to {target}: {json.dumps(data)[:80]}")

            elif act_type == "add_todo":
                target_person = target.split(".")[0] if "." in target else "arabelle"
                db.setdefault(target_person, {}).setdefault("todos", []).append(data)
                log(f"Added todo for {target_person}: {data.get('text', '')[:50]}")

        except Exception as e:
            log(f"Action failed ({target}): {e}")

    # Update timestamp and save
    db["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(DASHBOARD_DB, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    # Rebuild dashboard-data.json
    try:
        subprocess.run([PYTHON, str(BUILD_SCRIPT)], capture_output=True, timeout=15)
    except Exception as e:
        log(f"Build failed: {e}")


def log_observations(observations):
    """Log pattern observations to memory."""
    if not observations:
        return

    PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not PATTERNS_FILE.exists():
        PATTERNS_FILE.write_text(
            "---\nname: Arabelle Patterns\n"
            "description: Learned patterns from Arabelle's Telegram conversations\n"
            "type: project\n---\n\n# Arabelle Patterns\n\n"
        )

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(PATTERNS_FILE, "a") as f:
        for obs in observations:
            f.write(f"\n## {ts}\n")
            f.write(f"**Type:** {obs.get('type', 'unknown')}\n")
            f.write(f"**Detail:** {obs.get('detail', '')}\n")
            f.write(f"**Action:** {obs.get('action', '')}\n")

    log(f"Logged {len(observations)} observation(s)")


def process_message(text):
    """Process a single message: build prompt -> call Claude -> parse -> act -> respond."""
    log(f"Processing: {text[:50]}...")

    prompt = build_prompt(text)
    response = call_claude(prompt)

    if not response:
        return "Sorry, something went wrong on my end. Try again in a bit!"

    reply, actions, observations = parse_response(response)

    # Execute data actions
    execute_actions(actions)

    # Log observations
    log_observations(observations)

    return reply


def run_polling_loop():
    """Main polling loop."""
    log("Arabelle Bot started. Polling every 30s...")

    while running:
        updates = poll_updates()

        for update in updates:
            update_id = update.get("update_id", 0)
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")
            sender = message.get("from", {}).get("first_name", "Unknown")

            if not text:
                save_offset(update_id)
                continue

            log(f"From {sender}: {text[:80]}")
            log_conversation("Arabelle", text)

            # Process and respond
            reply = process_message(text)

            if reply:
                send_to_arabelle(reply)
                log(f"Replied: {reply[:80]}")

            save_offset(update_id)

        # Wait before next poll (unless shutting down)
        if running:
            time.sleep(POLL_INTERVAL)

    release_lock()
    log("Arabelle Bot stopped.")


def run_once():
    """Process pending messages once and exit."""
    log("Running once...")
    updates = poll_updates()

    for update in updates:
        update_id = update.get("update_id", 0)
        message = update.get("message", {})
        text = message.get("text", "")

        if text:
            reply = process_message(text)
            if reply:
                send_to_arabelle(reply)
                log(f"Replied: {reply[:80]}")

        save_offset(update_id)

    log(f"Processed {len(updates)} update(s).")


def test_message(text):
    """Test processing without Telegram."""
    log(f"Test mode: {text}")
    reply = process_message(text)
    print(f"\n--- REPLY ---\n{reply}\n")


if __name__ == "__main__":
    if "--test" not in sys.argv:
        acquire_lock()
    if "--once" in sys.argv:
        run_once()
    elif "--test" in sys.argv:
        idx = sys.argv.index("--test")
        msg = " ".join(sys.argv[idx + 1:]) if idx + 1 < len(sys.argv) else "hello"
        test_message(msg)
    else:
        run_polling_loop()
