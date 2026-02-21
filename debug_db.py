import sqlite3
import json

conn = sqlite3.connect('financial_plan.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM transactions ORDER BY date').fetchall()
print(json.dumps([dict(r) for r in rows], indent=2))
conn.close()
