from storage.db import get_db
db=get_db()
r=db.conn.execute("SELECT COUNT(*) FROM watchlist_daily WHERE date='2026-06-09'").fetchone()
b=db.conn.execute("SELECT b1_count,near_b1_count FROM b1_scan WHERE scan_id=23").fetchone()
print(f'wl_daily: {r[0]} | B1: {b[0]} near: {b[1]}')
