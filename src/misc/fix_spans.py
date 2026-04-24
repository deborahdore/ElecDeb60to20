"""
fix_spans.py

For each component (T-annotation) in an .ann file whose span does not produce
the correct text when extracted from the .txt file, the script applies one of
two strategies:

CONTINUOUS SPANS (single fragment)
  Searches for the annotated text in the .txt file and replaces the span with
  the correct position.

DISCONTINUOUS SPANS (multiple fragments, separated by ";")
  Tries to adjust the fragment boundaries so that direct concatenation of all
  fragments equals ann_text.  The ann_text field is never modified.
  If the boundaries cannot be adjusted to reproduce ann_text exactly, the
  component is reported as unfixable.

Usage
-----
    python fix_spans.py --ann /path/to/file.ann --txt /path/to/file.txt
    python fix_spans.py --ann /path/to/file.ann --txt /path/to/file.txt --dry-run
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_t_line(raw: str):
    """
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


def parse_fragments(span_str: str) -> list:
    """Return [(start, end), ...] for each fragment in span_str, or None on error."""
    result = []
    for seg in span_str.split(";"):
        seg = seg.strip()
        if not seg:
            continue
        parts = seg.split()
        if len(parts) != 2:
            return None
        try:
            result.append((int(parts[0]), int(parts[1])))
        except ValueError:
            return None
    return result or None


def extract_span(txt: str, span_str: str) -> str:
    """Extract and concatenate text fragments directly (no separator)."""
    frags = parse_fragments(span_str)
    if frags is None:
        return None
    return "".join(txt[s:e] for s, e in frags)


def find_in_txt(txt: str, ann_text: str, original_start: int) -> list:
    """
    Return all start positions where ann_text appears in txt.
    Sorted by distance from original_start so the closest hit comes first.
    """
    positions = [m.start() for m in re.finditer(re.escape(ann_text), txt)]
    positions.sort(key=lambda p: abs(p - original_start))
    return positions


def original_start(span_str: str) -> int:
    """Return the start offset of the first fragment in span_str."""
    try:
        return int(span_str.split(";")[0].strip().split()[0])
    except (ValueError, IndexError):
        return 0


def try_fix_discontinuous_span(txt: str, ann_text: str, span_str: str):
    """
    For a discontinuous span whose direct concatenation does not match ann_text,
    try to adjust the fragment boundaries so that direct concatenation does match.

    Strategy: walk through the fragments in order, matching each fragment's text
    against ann_text.  Between consecutive fragments, any separator that appears
    in ann_text but not in the raw concatenation is absorbed by nudging the
    boundary of one of the two adjacent fragments:
      1. Extend the left fragment's end to include the separator.
      2. Or shrink the right fragment's start to include the separator.
      3. Or find the separator anywhere in the gap and extend the left fragment
         to include it.

    Returns the corrected span_str if a fix was found, or None otherwise.
    The ann_text field is never changed.
    """
    frags = parse_fragments(span_str)
    if frags is None:
        return None
    n = len(frags)
    new_frags = [list(f) for f in frags]  # mutable copies
    ann_pos = 0  # cursor into ann_text

    for i in range(n):
        s, e = new_frags[i]
        frag_text = txt[s:e]

        # Current fragment must align with ann_text at ann_pos
        if ann_text[ann_pos:ann_pos + len(frag_text)] != frag_text:
            return None
        ann_pos += len(frag_text)

        if i < n - 1:
            next_s, next_e = new_frags[i + 1]
            next_frag_text = txt[next_s:next_e]

            # Find where the next fragment's text begins in ann_text
            next_ann_pos = ann_text.find(next_frag_text, ann_pos)
            if next_ann_pos == -1:
                return None

            sep = ann_text[ann_pos:next_ann_pos]  # separator present in ann_text
            if sep:
                gap_text = txt[e:next_s]  # characters between fragments in .txt
                if gap_text.startswith(sep):
                    # Absorb sep by extending current fragment's end
                    new_frags[i][1] = e + len(sep)
                elif gap_text.endswith(sep):
                    # Absorb sep by shrinking next fragment's start
                    new_frags[i + 1][0] = next_s - len(sep)
                elif sep in gap_text:
                    # Sep starts somewhere inside the gap — extend left fragment to cover it
                    idx = gap_text.find(sep)
                    new_frags[i][1] = e + idx + len(sep)
                else:
                    return None  # separator not found in gap — unfixable
            ann_pos = next_ann_pos

    # Verify the fix actually produces the correct text
    result = "".join(txt[s:e] for s, e in new_frags)
    if result == ann_text:
        return ";".join(f"{s} {e}" for s, e in new_frags)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix incorrect spans in a brat .ann file by searching for the "
                    "annotated text in the source .txt file."
    )
    parser.add_argument("--ann", required=True, help="Annotation file (.ann).")
    parser.add_argument("--txt", required=True, help="Plain-text source file (.txt).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would be fixed without writing the file.")
    args = parser.parse_args()

    ann_path = Path(args.ann)
    txt_path = Path(args.txt)

    if not ann_path.is_file():
        sys.exit(f"ERROR: annotation file not found: {ann_path}")
    if not txt_path.is_file():
        sys.exit(f"ERROR: text file not found: {txt_path}")

    txt = txt_path.read_text(encoding="utf-8")
    ann_lines = ann_path.read_text(encoding="utf-8").splitlines(keepends=True)

    if args.dry_run:
        print("(DRY-RUN — file will NOT be modified)\n")

    fixed_span = []  # continuous: span updated
    fixed_disc = []  # discontinuous: span boundaries adjusted
    already_ok = []  # span already correct
    unfixable = []  # could not be resolved
    new_lines = []

    for raw in ann_lines:
        parsed = parse_t_line(raw)

        if parsed is None:
            new_lines.append(raw)
            continue

        ann_id, ann_type, span_str, ann_text = parsed
        is_discontinuous = ";" in span_str
        extracted_direct = extract_span(txt, span_str)

        # ------------------------------------------------------------------ #
        # No mismatch — keep as-is                                            #
        # ------------------------------------------------------------------ #
        if extracted_direct is not None:
            extracted_direct = extracted_direct.lower()
            ann_text = ann_text.lower()
            if extracted_direct.strip() == ann_text.strip():
                already_ok.append(ann_id)
                new_lines.append(raw)
                continue

        # ------------------------------------------------------------------ #
        # DISCONTINUOUS SPAN — adjust boundaries to match ann_text            #
        # ------------------------------------------------------------------ #
        if is_discontinuous:
            new_span_str = try_fix_discontinuous_span(txt, ann_text, span_str)

            if new_span_str is None:
                unfixable.append((ann_id, span_str, ann_text, extracted_direct))
                new_lines.append(raw)
                continue

            if new_span_str == span_str:
                already_ok.append(ann_id)
                new_lines.append(raw)
                continue

            action = "would fix span" if args.dry_run else "fixed span"
            print(f"  {ann_id} ({ann_type}): {action}")
            print(f"    span was : {span_str}")
            print(f"    span now : {new_span_str}")
            updated_line = f"{ann_id}\t{ann_type} {new_span_str}\t{ann_text}\n"
            new_lines.append(updated_line)
            fixed_disc.append((ann_id, span_str, new_span_str))
            continue

        # ------------------------------------------------------------------ #
        # CONTINUOUS SPAN — search for ann_text in .txt and update span       #
        # ------------------------------------------------------------------ #
        orig_start = original_start(span_str)
        hits = find_in_txt(txt, ann_text, orig_start)

        if not hits:
            unfixable.append((ann_id, span_str, ann_text, extracted_direct))
            new_lines.append(raw)
            continue

        new_start = hits[0]
        new_end = new_start + len(ann_text)
        new_span = f"{new_start} {new_end}"

        if len(hits) > 1:
            print(f"  {ann_id}: text found {len(hits)} times — using closest to original "
                  f"(orig start {orig_start}, chosen {new_start})")

        action = "would fix span" if args.dry_run else "fixed span"
        print(f"  {ann_id} ({ann_type}): {action}  {span_str}  ->  {new_span}")

        updated_line = f"{ann_id}\t{ann_type} {new_span}\t{ann_text}\n"
        new_lines.append(updated_line)
        fixed_span.append((ann_id, span_str, new_span))

    if not args.dry_run and (fixed_span or fixed_disc):
        ann_path.write_text("".join(new_lines), encoding="utf-8")

    if unfixable:
        print(f"\nTruly unfixable — {len(unfixable)} component(s):")
        for ann_id, span_str, ann_text, extracted in unfixable:
            frags = span_str.count(";") + 1
            print(f"  {ann_id}  ({frags} fragment(s))  span: {span_str}")
            print(f"    ann_text : {ann_text}")
            print(f"    extracted: {extracted}")

    print(f"\nDone.")
    print(f"  Continuous spans fixed (span updated)              : {len(fixed_span)}")
    print(f"  Discontinuous spans fixed (span boundaries nudged) : {len(fixed_disc)}")
    print(f"  Already correct                                    : {len(already_ok)}")
    print(f"  Truly unfixable                                    : {len(unfixable)}")


if __name__ == "__main__":
    main()
