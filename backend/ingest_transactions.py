import os
import csv
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv


def main() -> None:
    # Load environment variables from .env at repo root
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set; ensure it is in .env or the environment")

    csv_path = project_root / "backend" / "synthetic-data" / "output_data" / "transactions.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found at {csv_path}")

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                # Ensure table exists
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS transactions (
                        transaction_id UUID PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        amount NUMERIC(18, 2) NOT NULL,
                        merchant_name TEXT NOT NULL,
                        merchant_category TEXT NOT NULL,
                        spending_category TEXT NOT NULL,
                        transaction_type TEXT NOT NULL,
                        payment_method TEXT NOT NULL,
                        city TEXT NOT NULL,
                        country TEXT NOT NULL,
                        currency TEXT NOT NULL
                    )
                    """
                )

                # Read CSV rows
                with csv_path.open(newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)

                if not rows:
                    print("No rows found in CSV; nothing to insert.")
                    return

                # Fetch existing transaction_ids so we can detect conflicts explicitly
                cur.execute("SELECT transaction_id FROM transactions;")
                existing_ids = {row[0] for row in cur.fetchall()}

                # Prepare data for bulk insert, logging any conflicts we detect client-side
                records = []
                for r in rows:
                    tx_id = r["transaction_id"]
                    if tx_id in existing_ids:
                        # Print the CSV row that would conflict
                        print(f"Conflict for transaction_id={tx_id}: {r}")
                        continue

                    records.append(
                        (
                            tx_id,
                            r["timestamp"],
                            float(r["amount"]),
                            r["merchant_name"],
                            r["merchant_category"],
                            r["spending_category"],
                            r["transaction_type"],
                            r["payment_method"],
                            r["city"],
                            r["country"],
                            r["currency"],
                        )
                    )

                # Count existing rows before insert (after filtering duplicates)
                cur.execute("SELECT COUNT(*) FROM transactions;")
                before = cur.fetchone()[0]

                # Insert data, ignoring duplicates on primary key
                insert_sql = """
                    INSERT INTO transactions (
                        transaction_id,
                        timestamp,
                        amount,
                        merchant_name,
                        merchant_category,
                        spending_category,
                        transaction_type,
                        payment_method,
                        city,
                        country,
                        currency
                    )
                    VALUES %s
                    ON CONFLICT (transaction_id) DO NOTHING
                """
                execute_values(cur, insert_sql, records, page_size=1000)

                # Report actual number of new rows
                cur.execute("SELECT COUNT(*) FROM transactions;")
                after = cur.fetchone()[0]
                print(f"Inserted {after - before} new transactions into the 'transactions' table.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

