---
paths:
  - "*.html"
  - "*.json"
  - "tools/**/*.py"
---

# Dashboard Rules

Deployed at: ra-dashboard-lake.vercel.app

## Data Rules
- No manual DB injection -- structured data flows through the pipeline only
- Narrative and context go to life-log, not the DB
- All edits post to Quick Log sheet + update UI instantly via localStorage
- Cash rules: pocket cash deducts on cash transactions, BPI only from screenshots

## UI Rules
- Pencil edit pattern: inline add/remove, always posts to Quick Log, updates UI instantly
- Bottom nav, hero clock, contextual insights -- preserve this structure
- Test locally before every deploy

## Deploy
- Use `/deploy` command after confirming changes look right locally
- Log every deploy in PROJECT_LOG.md (session number + what changed)
