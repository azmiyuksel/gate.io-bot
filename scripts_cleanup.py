"""Railway Postgres cleanup: truncate old paper trading data and reset account."""
import os
import sys

# Read DATABASE_URL from env (set by Railway)
db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("DATABASE_URL not found in env")
    sys.exit(1)

import psycopg

print(f"Connecting to database...")
conn = psycopg.connect(db_url, autocommit=True)
cur = conn.cursor()

# Show current counts
for table in ("paper_positions", "paper_orders", "paper_trades", "paper_logs", "paper_equity_curve"):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  {table}: {count} rows")

print("\nCleaning up...")

# Close open positions  
cur.execute("UPDATE paper_positions SET is_open = false, closed_at = NOW() WHERE is_open = true")
print(f"  paper_positions: closed {cur.rowcount} open positions")

# Truncate old data
cur.execute("DELETE FROM paper_logs WHERE created_at < NOW() - interval '2 days'")
print(f"  paper_logs: deleted {cur.rowcount} rows")

cur.execute("DELETE FROM paper_equity_curve")
print(f"  paper_equity_curve: deleted {cur.rowcount} rows")

# Reset paper account
cur.execute("UPDATE paper_accounts SET cash_balance = initial_balance, realized_pnl = 0, updated_at = NOW()")
print(f"  paper_accounts: reset {cur.rowcount} rows")

print("\nCleanup complete. New counts:")
for table in ("paper_positions", "paper_orders", "paper_trades", "paper_logs", "paper_equity_curve"):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  {table}: {count} rows")

cur.execute("SELECT id, name, status, cash_balance, initial_balance, realized_pnl FROM paper_accounts")
row = cur.fetchone()
if row:
    print(f"\nAccount: id={row[0]} name={row[1]} status={row[2]} cash={row[3]} initial={row[4]} pnl={row[5]}")

conn.close()
print("Done.")
