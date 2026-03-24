#!/bin/bash
# Auto-stamp last_updated and deploy to Vercel
cd "$(dirname "$0")"
TIMESTAMP=$(date -u -d '+8 hours' '+%Y-%m-%dT%H:%M:%S+08:00')
sed -i "s/\"last_updated\": \"[^\"]*\"/\"last_updated\": \"$TIMESTAMP\"/" dashboard-data.json
echo "Stamped: $TIMESTAMP"
vercel --prod
