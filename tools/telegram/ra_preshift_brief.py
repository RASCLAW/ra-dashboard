"""
RA Pre-Shift Brief -- sent via Rasclaw Telegram bot at 7 PM PHT.

Systems check + dashboard freshness + money + projects + heads up.
Everything RA needs to see before walking out the door for night shift.

Usage:
    python ra_preshift_brief.py              # Send to RA
    python ra_preshift_brief.py --dry-run    # Print without sending
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from send_message import send_to_ra, ENV

PHT = timezone(timedelta(hours=8))
DASHBOARD_DB = Path("/home/ra/projects/ra-dashboard/dashboard-db.json")
IMAGE_QUEUE = Path("/home/ra/projects/ra-dashboard/.tmp/image_queue.json")
PIPELINE = Path("/home/ra/projects/DuberyMNL/.tmp/pipeline.json")


def load_db():
    if not DASHBOARD_DB.exists():
        return None
    return json.loads(DASHBOARD_DB.read_text())


def check_process(name, pattern):
    """Check if a process matching pattern is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False


def check_lock(path):
    """Check if a lock file exists."""
    return Path(path).exists()


def check_cron(pattern):
    """Check if a cron job matching pattern exists."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=5
        )
        return pattern in result.stdout
    except:
        return False


def hours_since(date_str, time_str=None):
    """Calculate hours since a date+time string."""
    if not date_str:
        return float('inf')
    t = time_str or '12:00'
    t = t.strip()[:5]
    try:
        dt = datetime.fromisoformat(f"{date_str}T{t}:00+08:00")
        return (datetime.now(PHT) - dt).total_seconds() / 3600
    except:
        return float('inf')


def bill_days_left(bill):
    """Calculate days until bill due date."""
    if not bill.get('due_date'):
        return None
    try:
        today = datetime.now(PHT).strftime('%Y-%m-%d')
        today_ms = datetime.fromisoformat(f"{today}T00:00:00+08:00")
        due_ms = datetime.fromisoformat(f"{bill['due_date']}T00:00:00+08:00")
        return (due_ms - today_ms).days
    except:
        return None


def next_payday(db):
    """Find next payday from pay_schedule."""
    ps = db.get('shared', {}).get('pay_schedule', {})
    now = datetime.now(PHT)
    today = now.date()
    results = []

    # RA: semi-monthly
    if ps.get('ra', {}).get('type') == 'semi-monthly':
        days = ps['ra'].get('days', [15, 31])
        for offset in range(0, 45):
            d = today + timedelta(days=offset)
            if d.day in days or (31 in days and d.day == (d.replace(month=d.month % 12 + 1, day=1) - timedelta(days=1)).day):
                # Weekend check
                if d.weekday() == 5:  # Saturday
                    d -= timedelta(days=1)
                elif d.weekday() == 6:  # Sunday
                    d -= timedelta(days=2)
                if d >= today:
                    results.append(('RA', (d - today).days))
                    break

    # Arabelle: bi-weekly
    if ps.get('arabelle', {}).get('anchor'):
        anchor = datetime.fromisoformat(f"{ps['arabelle']['anchor']}T00:00:00+08:00").date()
        interval = ps['arabelle'].get('interval_days', 14)
        d = anchor
        while d < today:
            d += timedelta(days=interval)
        results.append(('Arabelle', (d - today).days))

    results.sort(key=lambda x: x[1])
    return results[0] if results else None


def build_brief():
    now = datetime.now(PHT)
    db = load_db()
    if not db:
        return "Could not load dashboard data."

    day_name = now.strftime('%a, %b %d')
    time_str = now.strftime('%I:%M %p')
    is_workday = now.weekday() < 5  # Mon-Fri

    lines = []

    # Greeting
    if is_workday:
        lines.append(f"<b>{day_name} | {time_str}</b>")
        lines.append("Shift tonight 8 PM - 5 AM")
    else:
        lines.append(f"<b>{day_name} | {time_str}</b>")
        lines.append("Rest day -- no shift tonight")

    # Systems
    systems = [
        ("Tunnel", check_process("tunnel", "code-tunnel") or check_process("code-server", "code-server")),
        ("Tunnel watchdog", check_lock("/home/ra/.vscode/cli/tunnel-stable.lock")),
        ("Belle", check_process("arabelle_bot", "arabelle_bot.py")),
        ("Dashboard cron", check_cron("dashboard_sync.py")),
        ("Belle watchdog", check_cron("belle_watchdog")),
    ]

    down = [name for name, running in systems if not running]
    if down:
        lines.append(f"\n\u26a0\ufe0f <b>{', '.join(down)}</b> {'is' if len(down)==1 else 'are'} down. Fix before you leave.")
    else:
        lines.append(f"\n\u2705 All systems running")

    # Baby Jah
    jah = db.get('shared', {}).get('baby_jah', {})
    feeds = jah.get('feeding', [])
    if feeds:
        last_f = feeds[-1]
        f_hrs = hours_since(last_f.get('date'), last_f.get('time'))
        food = last_f.get('food', '?')
        if f_hrs > 8:
            lines.append(f"\n\U0001f6a8 Jah hasn't eaten in <b>{f_hrs:.0f}h</b>. Last was {food}.")
        elif f_hrs > 4:
            lines.append(f"\n\U0001f37c Jah last ate {food}, {f_hrs:.0f}h ago")
        else:
            lines.append(f"\n\U0001f37c Jah ate {food} {f_hrs:.0f}h ago")

    # Dashboard staleness
    last_updated = db.get('last_updated', '')
    if last_updated:
        upd_hrs = hours_since(last_updated[:10], last_updated[11:16] if len(last_updated) > 11 else None)
        if upd_hrs > 12:
            lines.append(f"\u26a0\ufe0f Dashboard is <b>{upd_hrs:.0f}h stale</b>")

    # Money
    accts = db.get('shared', {}).get('accounts', {})
    payroll = accts.get('payroll', {}).get('balance', 0)
    pocket = accts.get('pocket_cash', {}).get('balance', 0)
    total = payroll + accts.get('savings', {}).get('balance', 0) + pocket
    lines.append(f"\n\U0001f4b0 <b>P{total:,.0f}</b> total")
    lines.append(f"Payroll P{payroll:,.0f} | Pocket P{pocket:,.0f}")

    pay = next_payday(db)
    if pay and pay[1] <= 3:
        if pay[1] == 0:
            lines.append(f"\U0001f389 <b>{pay[0]} payday today!</b>")
        elif pay[1] == 1:
            lines.append(f"\U0001f4b5 {pay[0]} payday tomorrow")
        else:
            lines.append(f"\U0001f4b5 {pay[0]} payday in {pay[1]} days")

    bills = [b for b in db.get('shared', {}).get('bills', {}).get('items', []) if b.get('status') != 'paid']
    for b in bills:
        dl = bill_days_left(b)
        if dl is not None and dl < 0:
            lines.append(f"\U0001f534 {b['name']} <b>P{b['amount']:,.0f}</b> -- {abs(dl)}d overdue")
        elif dl is not None and dl <= 5:
            lines.append(f"\U0001f7e1 {b['name']} P{b['amount']:,.0f} -- {dl}d left")

    # Projects
    builder = db.get('ra', {}).get('builder', {})
    projects = builder.get('projects', [])
    active = [p for p in projects if p.get('status') == 'in-progress']
    if active:
        lines.append(f"\n\U0001f6e0\ufe0f <b>{len(active)} active builds</b>")
        for p in active[:3]:
            lines.append(f"\u2022 <b>{p['name']}</b>")
            lines.append(f"  <i>{p.get('next','')}</i>")

    rq = builder.get('review_queue', {})
    queue_parts = []
    if rq.get('job_leads_unseen', 0) > 0:
        queue_parts.append(f"{rq['job_leads_unseen']} job leads")
    if rq.get('pipeline_pending', 0) > 0:
        queue_parts.append(f"{rq['pipeline_pending']} pipeline items")
    if rq.get('image_queue', 0) > 0:
        queue_parts.append(f"{rq['image_queue']} images")
    if queue_parts:
        lines.append(f"\n\U0001f4cb Waiting: {' | '.join(queue_parts)}")

    # Heads up
    heads_up = []
    briefing_updated = db.get('briefing', {}).get('updated', '')
    if briefing_updated:
        b_hrs = hours_since(briefing_updated)
        if b_hrs > 72:
            heads_up.append(f"briefing {int(b_hrs/24)}d old")

    scooter = db.get('shared', {}).get('vehicle', {}).get('scooter', {})
    gas = scooter.get('gas_level', '100%')
    gas_num = int(str(gas).replace('%', '')) if gas else 100
    if gas_num < 30:
        heads_up.append(f"scooter at {gas_num}%")

    ra_todos = [t for t in db.get('ra', {}).get('todos', []) if not t.get('done')]
    if ra_todos:
        heads_up.append(f"{len(ra_todos)} open todos")

    if heads_up:
        lines.append(f"\n\U0001f4ac {' | '.join(heads_up)}")

    return "\n".join(lines)


if __name__ == "__main__":
    brief = build_brief()

    if "--dry-run" in sys.argv:
        # Strip HTML tags for terminal display
        import re
        plain = re.sub(r'<[^>]+>', '', brief)
        print(plain)
    else:
        success = send_to_ra(brief)
        if success:
            print("Pre-shift brief sent to RA via Rasclaw.")
        else:
            print("Failed to send brief.")
