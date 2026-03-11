"""
Central entry point for synthetic transaction data generation.

Run from the synthetic-data directory:
    python main.py

Or from the repo root:
    python -m backend.synthetic-data.main
"""

from config import OUTPUT_DIR
from generator import generate_transactions, load_prompt
from writers import save_all, write_raw_debug


def run() -> None:
    """Generate transactions and save CSV + JSON to output_data."""
    print("Generating transactions... this may take a moment.")

    prompt = load_prompt()
    raw_csv = generate_transactions(prompt=prompt)

    try:
        csv_path, json_path = save_all(raw_csv)
        num_rows = len([line for line in raw_csv.split("\n") if line.strip()]) - 1
        print(f"Saved {num_rows} records to {OUTPUT_DIR}/")
        print(f"  - {csv_path.name}")
        print(f"  - {json_path.name}")
    except Exception as e:
        print(f"Error saving output: {e}")
        debug_path = write_raw_debug(raw_csv)
        print(f"Raw response saved to {debug_path}")


if __name__ == "__main__":
    run()
