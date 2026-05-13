"""
check_text_spans.py
--------------------
Verifies that the `text_span` column in fallacies_with_span.csv correctly
locates the `text` column inside the corresponding debate .txt file.

For each row the script:
  1. Resolves the txt file from `debate_id`  (e.g. "2_1960" -> "2_1960.txt")
  2. Reads the full file content as a single string
  3. Slices content[start:end] using the (start, end) values in `text_span`
  4. Compares the slice to the `text` column (after stripping leading/trailing
     whitespace from both sides)
  5. Reports mismatches, missing files, and a final summary

Usage:
    python check_text_spans.py
"""

import csv
import os
import ast
import re

# ── paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "../../data", "annotations", "fallacies",
                          "fallacies_with_span.csv")
TXT_DIR    = os.path.join(BASE_DIR, "../../data", "annotations", "txt")

# ── helpers ────────────────────────────────────────────────────────────────────
def parse_span(span_str):
    """Convert '(5196, 5474)' -> (5196, 5474).  Returns None on failure."""
    try:
        result = ast.literal_eval(span_str.strip())
        if isinstance(result, (tuple, list)) and len(result) == 2:
            return int(result[0]), int(result[1])
    except Exception:
        pass
    return None


def load_txt(debate_id, cache={}):
    """Return the full content of the debate txt file (cached)."""
    if debate_id in cache:
        return cache[debate_id]
    path = os.path.join(TXT_DIR, f"{debate_id}.txt")
    if not os.path.isfile(path):
        cache[debate_id] = None
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()
    cache[debate_id] = content
    return content


def normalise(s):
    """Strip leading/trailing whitespace for comparison."""
    return s.strip()

# ── main ───────────────────────────────────────────────────────────────────────
def main():
    total        = 0
    skipped_no_span   = 0
    skipped_no_file   = 0
    skipped_no_text   = 0
    ok           = 0
    mismatches   = []
    bad_spans    = []
    missing_files = set()

    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):   # row 2 = first data row
            debate_id = row.get("debate_id", "").strip()
            text_col  = row.get("text", "").strip()
            span_col  = row.get("text_span", "").strip()

            total += 1

            # ── skip rows with no span ──────────────────────────────────────
            if not span_col:
                skipped_no_span += 1
                continue

            # ── parse span ─────────────────────────────────────────────────
            span = parse_span(span_col)
            if span is None:
                bad_spans.append((row_num, debate_id, span_col))
                continue
            start, end = span

            # ── load txt file ──────────────────────────────────────────────
            content = load_txt(debate_id)
            if content is None:
                missing_files.add(debate_id)
                skipped_no_file += 1
                continue

            # ── skip rows with no text to compare ──────────────────────────
            if not text_col:
                skipped_no_text += 1
                continue

            # ── extract slice and compare ──────────────────────────────────
            extracted = content[start:end]
            if normalise(extracted) == normalise(text_col):
                ok += 1
            else:
                mismatches.append({
                    "row":       row_num,
                    "debate_id": debate_id,
                    "span":      (start, end),
                    "expected":  normalise(text_col),
                    "got":       normalise(extracted),
                })

    # ── report ─────────────────────────────────────────────────────────────────
    print("=" * 70)
    print("TEXT SPAN VERIFICATION REPORT")
    print("=" * 70)
    print(f"CSV              : {CSV_PATH}")
    print(f"TXT directory    : {TXT_DIR}")
    print(f"Total data rows  : {total}")
    print(f"  No span value  : {skipped_no_span}")
    print(f"  Unparseable span: {len(bad_spans)}")
    print(f"  Missing txt file: {skipped_no_file}  {sorted(missing_files) if missing_files else ''}")
    print(f"  No text value  : {skipped_no_text}")
    print(f"  Checked        : {ok + len(mismatches)}")
    print(f"  PASSED         : {ok}")
    print(f"  FAILED         : {len(mismatches)}")
    print("=" * 70)

    if bad_spans:
        print("\n── Unparseable spans ──")
        for row_num, did, s in bad_spans:
            print(f"  row {row_num:5d}  debate_id={did!r:15s}  span={s!r}")

    if mismatches:
        print(f"\n── Mismatches ({len(mismatches)}) ──")
        for m in mismatches:
            print(f"\n  row {m['row']:5d}  debate_id={m['debate_id']!r}  span={m['span']}")
            print(f"  EXPECTED : {m['expected'][:120]!r}{'...' if len(m['expected'])>120 else ''}")
            print(f"  GOT      : {m['got'][:120]!r}{'...' if len(m['got'])>120 else ''}")
    else:
        print("\nAll checked spans match their text values.")

    print("\nDone.")


if __name__ == "__main__":
    main()
