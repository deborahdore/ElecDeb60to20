"""Add a single SBERT (all-MiniLM-L6-v2) embedding per argument to every CSV
under data/annotations/arguments/. Each CSV represents one argument (a Claim
plus its supporting Premises, if any). The embedding is computed from the
concatenation of the Claim text and all Premise texts (in file order), and is
stored once, in the `embedding` column of the Claim row (JSON list of
6-decimal floats). Premise rows get an empty `embedding` cell. Each CSV is
overwritten in place.
"""
import csv
import glob
import json
import os

from sentence_transformers import SentenceTransformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGUMENTS_DIR = os.path.join(ROOT, "data", "annotations", "arguments")
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 256


def main():
    files = sorted(glob.glob(os.path.join(ARGUMENTS_DIR, "*", "*.csv")))
    print(f"Found {len(files)} CSV files")

    file_rows = []
    argument_texts = []
    for path in files:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        file_rows.append(rows)
        argument_texts.append(" ".join(r["text"] for r in rows))

    print(f"Encoding {len(argument_texts)} arguments with {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        argument_texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    fieldnames = ["role", "text", "original_label", "T_id", "start_char", "end_char", "embedding"]
    for path, rows, vec in zip(files, file_rows, embeddings):
        embedding_str = json.dumps([round(x, 6) for x in vec.tolist()])
        for row in rows:
            row["embedding"] = embedding_str if row["role"] == "Claim" else ""
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print("Done.")


if __name__ == "__main__":
    main()
