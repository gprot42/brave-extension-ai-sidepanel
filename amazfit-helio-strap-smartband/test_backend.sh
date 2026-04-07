#!/bin/bash
cd /Users/aicoder/src/amazfit-helio-strap-smartband
source backend/.venv/bin/activate

python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &
BGPID=$!
sleep 3

echo "=== Connect ==="
curl -s -X POST http://localhost:8000/api/connect
sleep 15

echo ""
echo "=== Activity after connect+sync ==="
curl -s 'http://localhost:8000/api/activity?limit=5'
echo ""

echo "=== Manual Sync ==="
curl -s -X POST http://localhost:8000/api/sync
sleep 10

echo ""
echo "=== Activity after manual sync ==="
curl -s 'http://localhost:8000/api/activity?limit=5'
echo ""

echo "=== DB Check ==="
python -c "
import sqlite3
conn = sqlite3.connect('helio_data.db')
cur = conn.cursor()
cur.execute('SELECT * FROM activity ORDER BY date DESC')
for r in cur.fetchall():
    print(r)
conn.close()
"

kill $BGPID 2>/dev/null
wait $BGPID 2>/dev/null
