#!/usr/bin/env python3
"""
extract_fallacies.py
Split the master fallacies CSV into one CSV file per debate.

Input:
  - fallacies CSV (CSV_PATH) with columns including 'debate_id'

Output:
  - one .csv file per debate written to CSV_OUT_DIR, named <debate_id>.csv
    e.g. data/fallacies/csv/1_1960.csv
"""

import os
import sys

import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSV_PATH    = os.path.join(BASE, "data", "annotations", "fallacies", "fallacies.csv")
CSV_OUT_DIR = os.path.join(BASE, "data", "fallacies", "csv")


# ── main ─────────────────────────────────────────────────────────────────────
def export_csv_per_debate(csv_path: str, csv_out_dir: str) -> None:
    """Read the master fallacies CSV and write one CSV per debate to *csv_out_dir*."""
    df = pd.read_csv(csv_path)

    if "debate_id" not in df.columns:
        print("ERROR: 'debate_id' column not found in the CSV.", file=sys.stderr)
        sys.exit(1)

    # Drop rows with no debate_id
    missing = df["debate_id"].isna() | (df["debate_id"].astype(str).str.strip() == "")
    if missing.any():
        print(f"  [WARN] {missing.sum()} row(s) have no debate_id and will be skipped.")
        df = df[~missing]

    os.makedirs(csv_out_dir, exist_ok=True)

    groups = df.groupby("debate_id", sort=True)
    for debate_id, group in groups:
        out_path = os.path.join(csv_out_dir, f"{debate_id}.csv")
        group.to_csv(out_path, index=False)
        print(f"  [OK]  {debate_id}  →  {debate_id}.csv  ({len(group)} row(s))", flush=True)

    print(f"\nDone: {len(groups)} CSV file(s) written to {csv_out_dir}")


def main():
    export_csv_per_debate(CSV_PATH, CSV_OUT_DIR)


if __name__ == "__main__":
    main()
