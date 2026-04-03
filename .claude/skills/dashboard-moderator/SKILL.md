---
name: dashboard-moderator
description: Use when syncing the family dashboard, refreshing dashboard data, updating Baby Jah tracking, reconciling finances, or deploying dashboard updates.
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Bash, Glob, Grep, AskUserQuestion
---

# Dashboard Moderator

Keeps the family life dashboard (ra-dashboard-lake.vercel.app) fresh by syncing data from multiple sources into `dashboard-db.json`, then deploying.

---

## Steps

### 1. Assess Current State

Read these files to understand what's stale:

- `dashboard-db.json` -- check `last_updated`, scan for outdated entries
- `life-log.md` -- check for entries newer than last DB sync
- `moderator-log.md` -- check last moderator action date

Report to RA:
- How many days stale the dashboard is
- What life-log entries haven't been synced
- Any bills past due date
- Any obvious gaps (empty fields, old balances)

### 2. Ask RA for Updates

Ask RA one round of questions covering all domains. Don't ask domains one at a time -- batch them:

```
Quick status check before I sync:

**Finances:**
- Current BPI payroll balance? (or "no change")
- Current pocket cash estimate?
- Any bills paid since [last_updated]?

**Baby Jah:**
- Recent feeding/sleep/diaper highlights? (or "use life-log")
- Any new milestones?

**Location:**
- Still in [current location]?

**Todos:**
- Anything to add/mark done?

**Other:**
- Anything else to capture?
```

Wait for RA's response before proceeding.

### 3. Present Change Plan

After gathering all inputs, present a summary of every change you plan to make:

```
Here's what I'll update in dashboard-db.json:

**Location:** [change or "no change"]
**Accounts:** [balance changes]
**Bills:** [status changes, new bills]
**Baby Jah:** [new entries count by type]
**Calendar:** [events added/removed]
**Todos:** [changes]
**Timeline:** [new entries]
**Briefing:** [updated or "skipped"]

Deploy to Vercel after? [y/n]
```

**Wait for RA's confirmation.** Do NOT write changes until confirmed.

### 4. Update dashboard-db.json

Apply changes in this order:

1. **last_updated** -- set to current PHT timestamp (`YYYY-MM-DDTHH:MM:SS+08:00`)
2. **location** -- update name/lat/lon if changed
3. **shared.accounts** -- update balances and notes. Rules:
   - Payroll (BPI): only update from screenshots or RA-confirmed numbers
   - Pocket cash: deduct on cash transactions, add on ATM withdrawals
   - Savings: update if RA confirms transfers
4. **shared.bills** -- mark paid (with paid_date), add new month's bills, flag overdue
5. **shared.baby_jah** -- append new entries to feeding, sleep, diapers, activities, milestones arrays
6. **shared.calendar** -- add upcoming events, remove past events older than 7 days
7. **ra.transactions** -- append new transactions with date, amount, category, method, note
8. **ra.todos** -- update status, add new items
9. **ra.sleep** -- append if RA reported sleep data
10. **arabelle.todos** -- update if applicable
11. **timeline** -- append new entries with timestamp and description
12. **briefing** -- update if older than 7 days (career, ai_news, local_news sections)
13. **shared.trips** -- mark completed trips, update status

Use the Edit tool for surgical changes. For large updates (many new entries), use Write to rewrite the full file.

### 5. Rebuild dashboard-data.json

```bash
cp dashboard-db.json dashboard-data.json
```

Then stamp the timestamp in dashboard-data.json (deploy.sh also does this, but be safe).

### 6. Deploy to Vercel

```bash
cd /c/Users/RAS/projects/ra-dashboard && bash deploy.sh
```

If deploy.sh fails (e.g., vercel CLI not installed), fall back to:
```bash
npx vercel --prod
```

### 7. Log the Session

Append to `moderator-log.md` using this format:

```markdown
## YYYY-MM-DD HH:MM (PHT)
**Type:** action
**Domain:** [comma-separated domains touched]
**Observation:** [one-line summary of what was synced]
**Data:**
- [bullet list of specific changes]
**Action:** Dashboard DB updated, dashboard-data.json rebuilt, deployed to Vercel
```

### 8. Confirm to RA

Tell RA:
- What was updated (brief)
- New dashboard-db.json last_updated timestamp
- Deploy status (success/fail)
- Any items that need follow-up

---

## Data Rules

- **No manual DB injection** -- all data flows through this moderator workflow
- **Narrative goes to life-log.md**, not dashboard-db.json
- **Cash rules:** pocket_cash deducts on cash transactions, BPI balance only from screenshots or RA confirmation
- **Idempotent:** safe to run multiple times -- same inputs produce same outputs
- **Never delete data** -- append new entries, update statuses, but don't remove historical records

## DB Schema Reference

```
dashboard-db.json
├── last_updated (ISO 8601 PHT)
├── location {name, lat, lon}
├── shared
│   ├── accounts {payroll, savings, pocket_cash}
│   ├── bills {month, items[], subscriptions[]}
│   ├── calendar []
│   ├── trips []
│   ├── baby_jah {feeding[], sleep[], diapers[], milestones[], activities[], health[]}
│   ├── buki {name, fed_today, last_vet, notes}
│   ├── kitchen {inventory[], meal_plan[], grocery_list[]}
│   └── patterns []
├── ra {schedule, transactions[], todos[], contacts[], sleep[], builder}
├── arabelle {schedule, transactions[], todos[], contacts[]}
├── logs []
├── timeline []
└── briefing {career[], ai_news[], local_news[], fuel, food, electricity}
```
