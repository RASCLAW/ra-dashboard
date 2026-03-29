"""
Morning Brief Generator for Arabelle (Belle).

Reads from a single canonical event source + dashboard-db.json,
generates a concise Taglish morning brief, sends via Telegram.

Usage:
    python morning_brief.py              # Send to Arabelle
    python morning_brief.py --dry-run    # Print without sending
    python morning_brief.py --to-ra      # Send preview to RA via Rasclaw

Architecture:
    fetch_today_events.py -> .tmp/today_events.json (single source of truth)
    morning_brief.py reads that + dashboard-db.json for finances/Jah
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from send_message import send_to_arabelle, send_telegram, ENV
from fetch_today_events import load_cached_events, cache_events

DASHBOARD_DB = Path("/home/ra/projects/ra-dashboard/dashboard-db.json")


def load_db():
    if not DASHBOARD_DB.exists():
        print("ERROR: dashboard-db.json not found")
        sys.exit(1)
    with open(DASHBOARD_DB) as f:
        return json.load(f)


def fmt(amount):
    if amount is None:
        return "?"
    return f"P{amount:,.0f}" if isinstance(amount, (int, float)) else f"P{amount}"


def to_12h(time_str):
    if not time_str:
        return ""
    try:
        h, m = map(int, time_str.split(":"))
        ampm = "AM" if h < 12 else "PM"
        h12 = h if h <= 12 else h - 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:{m:02d} {ampm}"
    except:
        return time_str


def build_brief(db, events):
    """Build the morning brief from clean event data + dashboard state."""
    today = datetime.now().strftime("%Y-%m-%d")
    day = datetime.now().strftime("%A")
    day_index = datetime.now().weekday()

    shared = db.get("shared", {})
    accounts = shared.get("accounts", {})
    bills = shared.get("bills", {}).get("items", [])
    baby_jah = shared.get("baby_jah", {})
    trips = shared.get("trips", [])
    location = db.get("location", {}).get("name", "Home")
    active_trip = next((t for t in trips if t.get("status") == "active"), None)

    lines = []

    # ─── HOOK (first 2 lines = notification preview) ───
    high_events = [e for e in events if e["priority"] == "high"]
    if len(high_events) >= 2:
        hook = f"{high_events[0]['title']} + {high_events[1]['title']}"
    elif high_events:
        hook = f"{high_events[0]['title']} today"
    elif events:
        hook = f"{events[0]['title']} today"
    else:
        hook = "Walang event today \u2615"

    lines.append("\u2600\uFE0F <b>Good morning, Maganda!</b>")
    lines.append(f"\U0001F4CC {hook}")
    lines.append(f"<i>{day} \u2022 {location}</i>")
    lines.append("")

    # ─── PACKED DAY NOTE ───
    if len(events) >= 4:
        lines.append(f"\U0001F525 <i>Packed day! {len(events)} events lined up.</i>")
        lines.append("")

    # ─── SCHEDULE ───
    if events:
        lines.append("\U0001F4C5 <b>TODAY</b>")
        # Sort by time for display
        display_events = sorted(events, key=lambda e: int(e["time"].replace(":", "")) if e["time"] else 9999)
        for e in display_events:
            t = to_12h(e["time"])
            if t:
                lines.append(f"  <b>{t}</b> \u2014 {e['title']}")
            else:
                lines.append(f"  \u2022 {e['title']}")
            if e.get("notes"):
                lines.append(f"       <i>{e['notes']}</i>")
        lines.append("")
    else:
        lines.append("\U0001F4C5 Walang event today. Chill day! \u2615")
        lines.append("")

    # ─── BUDGET ───
    payroll = accounts.get("payroll", {}).get("balance", 0)
    pocket = accounts.get("pocket_cash", {}).get("balance", 0)
    total = payroll + pocket
    pending = [b for b in bills if b.get("status") == "pending"]

    lines.append("\U0001F4B0 <b>BUDGET</b>")
    lines.append(f"  \U0001F4B5 Available: <b>{fmt(total)}</b>")
    if pending:
        for b in pending[:2]:
            lines.append(f"  \u26A0\uFE0F {b['name']} <b>{fmt(b['amount'])}</b> due {b.get('due_day', '?')}")
    lines.append("")

    # ─── BUJAH (insights only, not raw data) ───
    feedings = baby_jah.get("feedings", [])
    diapers = baby_jah.get("diapers", [])
    sleep = baby_jah.get("sleep", [])

    jah_insights = []

    # Feeding insight
    if feedings:
        last_feed = feedings[-1]
        notes = last_feed.get("notes", "")
        food = last_feed.get("food", "")
        if "less than usual" in notes.lower() or "less" in food.lower():
            jah_insights.append("Konti kain kahapon -- watch his appetite today")
        elif "excited" in notes.lower() or "hyper" in notes.lower():
            jah_insights.append("Super hyper kahapon -- baka gutom sya pagkagising")

    if not feedings:
        jah_insights.append("Walang feeding na-log kahapon -- check kung kumain na")

    # Sleep insight
    if sleep:
        last_sleep = sleep[-1]
        if last_sleep.get("slept") and not last_sleep.get("woke"):
            slept_time = last_sleep.get("slept", "")
            try:
                h = int(slept_time.split(":")[0])
                if h < 19:
                    jah_insights.append("Maaga natulog -- baka maaga din gising")
                elif h > 22:
                    jah_insights.append("Late natulog -- hayaan mo muna magpahinga")
            except:
                pass

    # Diaper insight
    if diapers:
        last_diaper = diapers[-1]
        if last_diaper.get("type", "").lower() == "poop":
            poop_count = sum(1 for d in diapers[-5:] if d.get("type", "").lower() == "poop")
            if poop_count >= 3:
                jah_insights.append("Medyo maraming poop lately -- normal but watch")

    # Trip/activity insight
    if active_trip:
        jah_insights.append("Vacation mode -- let him explore, keep hydrated")

    # Default if no insights
    if not jah_insights:
        jah_insights.append("All good! Normal routine kahapon")

    lines.append("\U0001F476 <b>BUJAH</b>")
    for insight in jah_insights[:2]:  # Max 2 insights
        lines.append(f"  \u2022 {insight}")
    lines.append("")

    # ─── FOOD IDEA ───
    meals = [
        "Chicken giniling + chayote \u2014 mash lang for Jah",
        "Tinolang manok \u2014 healthy, maraming sabaw",
        "Adobong manok \u2014 classic! Pwede ni Jah yung sauce",
        "Ginisang kangkong + pritong isda \u2014 budget, may gulay",
        "Pork sinigang \u2014 sabaw-heavy, easy i-share",
        "Tortang talong + sardinas \u2014 quick, kaya ni Jah",
        "Chicken sopas \u2014 comfort food, perfect pag maulan",
    ]
    meal_2 = meals[(day_index + 3) % len(meals)]  # offset for variety
    lines.append(f"\U0001F372 <b>FOOD IDEAS</b>")
    lines.append(f"  \u2022 {meals[day_index]}")
    lines.append(f"  \u2022 {meal_2}")
    lines.append("")

    # ─── HEALTH NUDGE ───
    is_trip = active_trip is not None
    is_weekend = day_index >= 5
    is_wfh = day_index in [0, 4]

    if is_trip:
        nudges = [
            "Enjoy the trip! Hydrate kayo ni Jah \U0001F4A7",
            "Vacation mode! Pero kumain ka on time ha \U0001F60A",
            "Lakad-lakad kayo, good for the whole family \U0001F6B6",
            "Fresh air sa province hits different \U0001F333",
            "Sunscreen ni Jah ha! Sensitive pa skin nya \u2600\uFE0F",
            "Take photos today \U0001F4F8 memories are priceless",
            "Rest well tonight, recharge for bukas \U0001F319",
        ]
    elif is_weekend:
        nudges = [
            "Weekend! Do something fun for yourself \U0001F389",
            "Rest day. Recharge para productive next week \U0001F4AA",
            "Lakad kayo ni Jah sa labas, fresh air \U0001F343",
            "Cook something new? Baka gusto ni Jah \U0001F373",
        ]
    elif is_wfh:
        nudges = [
            "WFH day -- stand up every hour, 2 min walk \U0001F6B6",
            "Stretch between calls, your back will thank you \U0001F64F",
            "Tubig, hindi lang kape! Hydrate \U0001F4A7",
        ]
    else:
        nudges = [
            "Stretch ka today, even 5 min helps \U0001F64F",
            "Hydrate! Target 8 glasses \U0001F4A7",
            "Kumain ng gulay today ha \U0001F966",
            "Rest pag nap ni Jah -- deserve mo yan \U0001F4A4",
        ]

    nudge = nudges[day_index % len(nudges)]
    lines.append(f"<i>{nudge}</i>")
    lines.append("")

    # ─── REPLY PROMPT (teach her Belle is two-way) ───
    prompts = [
        'Ask me about budget, food ideas, or baby tips \U0001F4AC',
        'I can help with meal ideas, reminders, or schedule \U0001F4AC',
        'Try asking me for food ideas or baby eating tips \U0001F4AC',
        'Need meal inspo, budget check, or Jah tips? Just ask \U0001F4AC',
        'I know your schedule, budget, and baby tips -- ask away \U0001F4AC',
        'Ask me anything -- food ideas, reminders, parenting tips \U0001F4AC',
        'Want food ideas? Baby tips? Budget check? Just reply \U0001F4AC',
    ]
    lines.append(f"<i>{prompts[day_index % len(prompts)]}</i>")

    return "\n".join(lines)


SENT_FLAG = Path("/home/ra/projects/ra-dashboard/.tmp/brief_sent_today")


def already_sent_today():
    """Check if a brief was already sent today."""
    if not SENT_FLAG.exists():
        return False
    flag_date = SENT_FLAG.read_text().strip()
    today = datetime.now().strftime("%Y-%m-%d")
    return flag_date == today


def mark_sent():
    """Mark today's brief as sent."""
    SENT_FLAG.parent.mkdir(parents=True, exist_ok=True)
    SENT_FLAG.write_text(datetime.now().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    db = load_db()
    events = cache_events()  # Always refresh when running directly
    brief = build_brief(db, events)

    if "--dry-run" in sys.argv:
        print(brief)
        print("\n--- DRY RUN: Not sent ---")
    elif "--to-ra" in sys.argv:
        token = ENV.get("RASCLAW_TG_BOT_TOKEN")
        chat_id = ENV.get("RASCLAW_TG_CHAT_ID")
        success = send_telegram(token, chat_id, brief)
        print("Sent to RA!" if success else "Failed")
    elif "--force" in sys.argv:
        success = send_to_arabelle(brief, label="Belle (Morning Brief)")
        if success:
            mark_sent()
        print("Morning brief force-sent!" if success else "Failed")
    else:
        if already_sent_today():
            print("Brief already sent today. Use --force to resend.")
        else:
            success = send_to_arabelle(brief, label="Belle (Morning Brief)")
            if success:
                mark_sent()
            print("Morning brief sent to Belle!" if success else "Failed")
