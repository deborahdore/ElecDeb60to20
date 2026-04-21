"""
verify_spans.py

For each component (T-annotation) in an .ann file, extracts the span from the
corresponding .txt file and checks whether the extracted text matches the
annotated text.  Mismatches are printed to the terminal.

Handles discontinuous spans (e.g. "100 150;200 250").

Usage
-----
    python verify_spans.py --ann /path/to/file.ann --txt /path/to/file.txt
"""

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_t_line(raw: str):
    """
    Parse a T-annotation line.
    Returns (ann_id, ann_type, span_str, ann_text) or None.
    """
    line = raw.rstrip("\n")
    if not line.startswith("T"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return None
    tokens = parts[1].strip().split(None, 1)
    ann_id = parts[0].strip()
    ann_type = tokens[0]
    span_str = tokens[1] if len(tokens) > 1 else ""
    ann_text = parts[2].strip()
    return ann_id, ann_type, span_str, ann_text


def extract_span(txt: str, span_str: str) -> str:
    """
    Extract and concatenate text for a (possibly discontinuous) span string.
    e.g. "100 150;200 250" -> txt[100:150] + txt[200:250]
    """
    fragments = []
    for segment in span_str.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        parts = segment.split()
        if len(parts) != 2:
            return None  # malformed span
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        fragments.append(txt[start:end])
    return "".join(fragments)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Verify that annotation spans in an .ann file match the text in a .txt file."
    )
    parser.add_argument("--ann", required=True, help="Annotation file (.ann).")
    parser.add_argument("--txt", required=True, help="Plain-text source file (.txt).")
    args = parser.parse_args()

    ann_path = Path(args.ann)
    txt_path = Path(args.txt)

    if not ann_path.is_file():
        sys.exit(f"ERROR: annotation file not found: {ann_path}")
    if not txt_path.is_file():
        sys.exit(f"ERROR: text file not found: {txt_path}")

    txt = txt_path.read_text(encoding="utf-8")
    lines = ann_path.read_text(encoding="utf-8").splitlines()

    total = 0
    mismatches = 0

    for raw in lines:
        parsed = parse_t_line(raw)
        if parsed is None:
            continue
        ann_id, ann_type, span_str, ann_text = parsed
        total += 1

        extracted = extract_span(txt, span_str)

        if extracted is None:
            print(f"  {ann_id}: malformed span '{span_str}'")
            mismatches += 1
            continue

        if extracted.strip() != ann_text.strip():
            print(f"  {ann_id} ({ann_type})  span: {span_str}")
            print(f"    annotated : {ann_text}")
            print(f"    from .txt : {extracted}")
            mismatches += 1

    print(f"\nChecked {total} component(s): {mismatches} mismatch(es) found.")


if __name__ == "__main__":
    main()
