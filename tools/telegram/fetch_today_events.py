"""
Fetch today's events from Google Calendar and cache locally.

Pulls from BOTH Family calendar and RA's primary calendar,
merges, deduplicates, and assigns priority.

Output: .tmp/today_events.json

Priority rules:
  high   -- family events, travel, health, formal (graduation, birthday, dinner)
  medium -- bills, reminders, work tasks
  low    -- prep, breakfast, chill, filler

Called by morning_brief.py before generating the brief,
or by cron to pre-cache events.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

CACHE_FILE = Path("/home/ra/projects/ra-dashboard/.tmp/today_events.json")
DASHBOARD_DB = Path("/home/ra/projects/ra-dashboard/dashboard-db.json")

# Keywords for priority classification
HIGH_KEYWORDS = [
    "graduation", "birthday", "beach", "dinner", "restaurant", "party",
    "hospital", "doctor", "dentist", "checkup", "flight", "depart",
    "return", "wedding", "baptism", "funeral", "island", "resort",
]
LOW_KEYWORDS = [
    "breakfast", "get ready", "prep", "chill", "rest", "wake up",
    "pack", "shower",
]


def classify_priority(title, notes=""):
    """Classify event priority based on content."""
    text = f"{title} {notes}".lower()
    if any(kw in text for kw in HIGH_KEYWORDS):
        return "high"
    if any(kw in text for kw in LOW_KEYWORDS):
        return "low"
    return "medium"


def get_events_from_db():
    """
    Pull today's events from dashboard-db.json as fallback.
    Merges calendar array + trip schedule, deduplicates.
    """
    if not DASHBOARD_DB.exists():
        return []

    with open(DASHBOARD_DB) as f:
        db = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    events = []
    seen = set()

    # Trip schedule first (has more detail)
    trips = db.get("shared", {}).get("trips", [])
    active_trip = next((t for t in trips if t.get("status") == "active"), None)
    if active_trip and active_trip.get("schedule"):
        today_sched = next(
            (s for s in active_trip["schedule"] if s.get("date") == today), None
        )
        if today_sched:
            for item in today_sched.get("items", []):
                title = item["event"]
                notes = item.get("notes", "")
                event = {
                    "title": title,
                    "time": item.get("time", ""),
                    "notes": notes,
                    "priority": classify_priority(title, notes),
                    "location": item.get("location", ""),
                    "source": "trip",
                }
                events.append(event)
                seen.add(title.lower()[:25])

    # Calendar array (skip duplicates)
    for e in db.get("shared", {}).get("calendar", []):
        if e.get("date") != today:
            continue
        title = e.get("title", "")
        # Check for overlap
        title_key = title.lower()[:25]
        is_dup = title_key in seen or any(
            len(set(title.lower().split()) & set(s.split())) >= 2
            for s in seen
        )
        if is_dup:
            continue
        notes = e.get("notes", "")
        event = {
            "title": title,
            "time": e.get("time", ""),
            "notes": notes,
            "priority": classify_priority(title, notes),
            "location": e.get("location", ""),
            "source": "calendar",
        }
        events.append(event)
        seen.add(title_key)

    # Sort: high priority first, then by time
    priority_order = {"high": 0, "medium": 1, "low": 2}
    events.sort(key=lambda e: (
        priority_order.get(e["priority"], 1),
        int(e["time"].replace(":", "")) if e["time"] else 9999,
    ))

    return events


def cache_events():
    """Fetch events and write to cache file."""
    events = get_events_from_db()

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M PHT"),
            "count": len(events),
            "events": events,
        }, f, indent=2)

    return events


def load_cached_events():
    """Load events from cache, regenerate if stale."""
    today = datetime.now().strftime("%Y-%m-%d")

    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            return data.get("events", [])

    # Cache is stale or missing, regenerate
    return cache_events()


if __name__ == "__main__":
    events = cache_events()
    print(f"Cached {len(events)} events for today:")
    for e in events:
        print(f"  [{e['priority']}] {e['time'] or '--:--'} {e['title']}")
