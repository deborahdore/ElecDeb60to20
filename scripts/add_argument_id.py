"""Add an `argument_id` column to every argument CSV under
data/annotations/arguments/. The ID is `ARG-<debate>-T<claim_T_id>` (e.g.
ARG-38_2012-T255), built from the debate folder name and the Claim's T_id
(the filename already matches the Claim's T_id). It is globally unique
across the corpus and traceable back to the source annotation, and is the
same for every row (Claim + Premises) within a given argument's CSV.
"""
import csv
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGUMENTS_DIR = os.path.join(ROOT, "data", "annotations", "arguments")

FIELDNAMES = [
    "argument_id", "role", "text", "original_label", "T_id", "start_char",
    "end_char", "speaker", "date", "embedding",
]


def main():
    files = sorted(glob.glob(os.path.join(ARGUMENTS_DIR, "*", "*.csv")))
    print(f"Found {len(files)} CSV files")

    for path in files:
        debate = os.path.basename(os.path.dirname(path))
        claim_tid = re.match(r"(T\d+)_argument\.csv$", os.path.basename(path)).group(1)
        argument_id = f"ARG-{debate}-{claim_tid}"

        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            row["argument_id"] = argument_id
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    print("Done.")


if __name__ == "__main__":
    main()
