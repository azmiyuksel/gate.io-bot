import psycopg

conn = psycopg.connect(
    "postgresql://postgres:qHTVNtlvicdvUzjJfXwVWcEBjOBcCgYw@thomas.proxy.rlwy.net:12929/railway"
)
conn.execute("ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS side VARCHAR(8) NOT NULL DEFAULT 'buy'")
conn.execute("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(32)")
conn.commit()
conn.close()
print("DB columns added OK")
