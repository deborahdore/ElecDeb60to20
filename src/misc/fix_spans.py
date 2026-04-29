"""
fix_spans.py

For each component (T-annotation) in an .ann file whose span does not produce
the correct text when extracted from the .txt file, the script applies one of
two strategies:

CONTINUOUS SPANS (single fragment)
  Searches for the annotated text in the .txt file (case-sensitive,
  punctuation-insensitive) and replaces the span with the correct position.
  If no punctuation-insensitive match is found, falls back to an approximate
  search using Levenshtein edit distance (threshold: < 5 edits).
  The ann_text field is then updated to the verbatim text at that position.

DISCONTINUOUS SPANS (multiple fragments, separated by ";")
  Two strategies are tried in order:
  1. Boundary nudge: adjusts fragment boundaries to absorb separator drift
     when each fragment's text already appears in ann_text.
  2. Piece search: when offsets are significantly wrong, splits ann_text at
     word boundaries and searches for each piece in txt near the original
     fragment position (punct-insensitive).
  The ann_text field is updated to the verbatim concatenation once found.
  If neither strategy succeeds, the component is reported as unfixable.

In both cases the ann_text field in the .ann file is rewritten to match the
source .txt file exactly (including punctuation).

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

_PUNCT_RE = re.compile(r'[^\w\s]')


def strip_punct(text: str) -> str:
    """Remove all punctuation for comparison purposes (keeps case and whitespace)."""
    return _PUNCT_RE.sub('', text)


def spans_match(a: str, b: str) -> bool:
    """Case-sensitive, punctuation-insensitive equality check."""
    return strip_punct(a).strip() == strip_punct(b).strip()


def punct_insensitive_pattern(text: str) -> str:
    """
    Build a regex that matches *text* case-sensitively, treating every run of
    punctuation characters as ``[^\\w\\s]*`` (zero or more punctuation chars).
    Word characters and spaces are matched literally.
    """
    result = []
    i = 0
    while i < len(text):
        if _PUNCT_RE.match(text[i]):
            # Collapse the whole punctuation run into one flexible token
            while i < len(text) and _PUNCT_RE.match(text[i]):
                i += 1
            result.append(r'[^\w\s]*')
        else:
            result.append(re.escape(text[i]))
            i += 1
    return ''.join(result)


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
    Return all re.Match objects where ann_text appears in txt (case-sensitive,
    punctuation-insensitive), sorted by distance from original_start so the
    closest hit comes first.
    """
    pattern = punct_insensitive_pattern(ann_text)
    try:
        matches = list(re.finditer(pattern, txt))
    except re.error:
        return []
    matches.sort(key=lambda m: abs(m.start() - original_start))
    return matches


def levenshtein_bounded(a: str, b: str, max_dist: int) -> int:
    """
    Standard Levenshtein distance with early termination: returns max_dist + 1
    as soon as the running minimum for any row exceeds max_dist.
    """
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            val = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb))
            curr.append(val)
            row_min = min(row_min, val)
        if row_min > max_dist:
            return max_dist + 1
        prev = curr
    return prev[-1]


def find_in_txt_fuzzy(
    txt: str, ann_text: str, original_start: int, max_dist: int = 8
) -> list:
    """
    Approximate search: slide a window over txt checking every substring whose
    length is within max_dist of len(ann_text).  Returns a list of
    (start, end, distance, matched_text) for all windows with
    levenshtein_bounded <= max_dist, sorted by (distance, distance from
    original_start).  Only the best (lowest-distance) hit per start offset is
    kept when multiple window lengths match the same position.
    """
    n = len(ann_text)
    best: dict = {}  # start -> (start, end, dist, text)

    for length in range(max(1, n - max_dist), n + max_dist + 1):
        for start in range(len(txt) - length + 1):
            window = txt[start : start + length]
            dist = levenshtein_bounded(ann_text, window, max_dist)
            if dist <= max_dist:
                if start not in best or dist < best[start][2]:
                    best[start] = (start, start + length, dist, window)

    results = list(best.values())
    results.sort(key=lambda x: (x[2], abs(x[0] - original_start)))
    return results


def original_start(span_str: str) -> int:
    """Return the start offset of the first fragment in span_str."""
    try:
        return int(span_str.split(";")[0].strip().split()[0])
    except (ValueError, IndexError):
        return 0


def try_fix_discontinuous_span(txt: str, ann_text: str, span_str: str):
    """
    Two-strategy approach to fix a discontinuous span whose concatenated text
    does not match ann_text (case-sensitive, punctuation-insensitive).

    Strategy 1 — boundary nudge (fast path):
      Walks through fragments in order.  Each fragment's verbatim text must
      appear in ann_text at the current cursor; separator characters that appear
      in ann_text between consecutive fragments are absorbed by nudging the
      adjacent fragment boundaries.  Works when the offsets are close to correct
      but gaps/overlaps have drifted by a few characters.

    Strategy 2 — piece search (fallback):
      Ignores fragment offsets entirely.  Splits ann_text at word-boundary
      positions into N pieces, ranks candidate splits by proximity to a
      proportional target derived from original fragment lengths, and for each
      candidate split searches for the piece in txt near the original fragment
      position (punct-insensitive regex).  Works when offsets are significantly
      wrong and the fragment text bears no relation to ann_text.

    Returns (corrected_span_str, actual_text) or (None, None).
    """
    frags = parse_fragments(span_str)
    if frags is None:
        return None, None

    result = _boundary_nudge(txt, ann_text, frags)
    if result[0] is not None:
        return result

    return _search_for_pieces(txt, ann_text, frags)


def _boundary_nudge(txt: str, ann_text: str, frags: list):
    """Strategy 1: nudge fragment boundaries to absorb separator drift."""
    n = len(frags)
    new_frags = [list(f) for f in frags]
    ann_pos = 0

    for i in range(n):
        s, e = new_frags[i]
        frag_text = txt[s:e]

        if ann_text[ann_pos:ann_pos + len(frag_text)] != frag_text:
            return None, None
        ann_pos += len(frag_text)

        if i < n - 1:
            next_s, next_e = new_frags[i + 1]
            next_frag_text = txt[next_s:next_e]

            next_ann_pos = ann_text.find(next_frag_text, ann_pos)
            if next_ann_pos == -1:
                return None, None

            sep = ann_text[ann_pos:next_ann_pos]
            if sep:
                gap_text = txt[e:next_s]
                if gap_text.startswith(sep):
                    new_frags[i][1] = e + len(sep)
                elif gap_text.endswith(sep):
                    new_frags[i + 1][0] = next_s - len(sep)
                elif sep in gap_text:
                    idx = gap_text.find(sep)
                    new_frags[i][1] = e + idx + len(sep)
                else:
                    return None, None
            ann_pos = next_ann_pos

    actual_text = "".join(txt[s:e] for s, e in new_frags)
    if spans_match(actual_text, ann_text):
        return ";".join(f"{s} {e}" for s, e in new_frags), actual_text
    return None, None


def _split_positions(text: str) -> list:
    """Positions in text immediately after each whitespace run (valid word-boundary splits)."""
    positions = set()
    for m in re.finditer(r'\s+', text):
        positions.add(m.end())
    return sorted(positions)


def _find_piece(txt: str, piece: str, near: int, radius: int = 500) -> tuple:
    """
    Find `piece` in txt[max(0, near-radius) : near+radius+len(piece)] using a
    punct-insensitive regex.  Returns (start, end) for the match closest to
    `near`, or None if no match is found.
    """
    lo = max(0, near - radius)
    hi = min(len(txt), near + radius + len(piece))
    pattern = punct_insensitive_pattern(piece)
    try:
        matches = list(re.finditer(pattern, txt[lo:hi]))
    except re.error:
        return None
    if not matches:
        return None
    best = min(matches, key=lambda m: abs((lo + m.start()) - near))
    return lo + best.start(), lo + best.end()


def _search_for_pieces(txt: str, ann_text: str, frags: list, radius: int = 300):
    """
    Strategy 2: split ann_text at word boundaries into N pieces and locate
    each piece in txt near its corresponding original fragment.

    Split candidates for each boundary are sorted by distance from a
    proportional target (based on original fragment lengths) so the most
    natural split is tried first.  The search is recursive; the first
    fully-consistent assignment is returned.
    """
    n = len(frags)
    ann_len = len(ann_text)

    # Special case: single fragment (shouldn't reach here, but be safe)
    if n == 1:
        hit = _find_piece(txt, ann_text, frags[0][0], radius)
        if hit:
            actual = txt[hit[0]:hit[1]]
            if spans_match(actual, ann_text):
                return f"{hit[0]} {hit[1]}", actual
        return None, None

    # Proportional split targets in ann_text based on original fragment lengths
    orig_lengths = [e - s for s, e in frags]
    total_orig = sum(orig_lengths) or 1
    cumulative = 0
    prop_targets = []
    for length in orig_lengths[:-1]:
        cumulative += length
        prop_targets.append(int(round(cumulative * ann_len / total_orig)))

    # Word-boundary split candidates in ann_text
    word_splits = _split_positions(ann_text)
    # Fall back to every character position if no whitespace (e.g. very short text)
    if not word_splits:
        word_splits = list(range(1, ann_len))

    def recurse(depth: int, ann_from: int, min_txt_end: int):
        """
        Find fragment positions for frags[depth:] that match ann_text[ann_from:].
        min_txt_end: the txt position after which new fragments must start.
        Returns a list of (start, end) pairs, or None if no valid assignment found.
        """
        frag_s, frag_e = frags[depth]
        # Respect the ordering constraint: this fragment must start after the
        # previous one ended in txt.
        near = max(frag_s, min_txt_end)

        if depth == n - 1:
            # Last fragment: must match exactly the rest of ann_text
            piece = ann_text[ann_from:]
            if not piece:
                return None
            hit = _find_piece(txt, piece, near, radius)
            if hit and hit[0] >= min_txt_end:
                return [hit]
            return None

        # Internal fragment: try each word-boundary split sorted by closeness
        # to the proportional target for this boundary
        target = prop_targets[depth]
        # Only consider splits that leave at least one character per remaining piece
        valid = [
            c for c in word_splits
            if ann_from < c <= ann_len - (n - depth - 1)
        ]
        valid.sort(key=lambda c: abs(c - target))

        for split in valid:
            piece = ann_text[ann_from:split]
            if not piece:
                continue
            hit = _find_piece(txt, piece, near, radius)
            if hit is None or hit[0] < min_txt_end:
                continue
            rest = recurse(depth + 1, split, hit[1])
            if rest is not None:
                return [hit] + rest

        return None

    solution = recurse(0, 0, 0)
    if solution is None:
        return None, None

    actual_text = "".join(txt[s:e] for s, e in solution)
    if spans_match(actual_text, ann_text):
        new_span_str = ";".join(f"{s} {e}" for s, e in solution)
        return new_span_str, actual_text
    return None, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix incorrect spans in a brat .ann file (case-sensitive, "
                    "punctuation-insensitive) and update ann_text to the verbatim "
                    "source text."
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

    fixed_span = []       # continuous: span offsets updated (punct-insensitive)
    fixed_fuzzy = []      # continuous: span offsets updated (edit-distance fallback)
    fixed_disc = []       # discontinuous: span boundaries nudged
    fixed_text_only = []  # span was correct, only ann_text punctuation updated
    already_ok = []       # span and ann_text both correct
    unfixable = []        # could not be resolved
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
        # Check current span (case-sensitive, punctuation-insensitive)        #
        # ------------------------------------------------------------------ #
        if extracted_direct is not None and spans_match(extracted_direct, ann_text):
            if extracted_direct.strip() == ann_text.strip():
                # Perfect verbatim match — nothing to do
                already_ok.append(ann_id)
                new_lines.append(raw)
            else:
                # Span offsets are correct but ann_text differs in punctuation;
                # rewrite ann_text to match the source exactly
                action = "would update text" if args.dry_run else "updated text"
                print(f"  {ann_id} ({ann_type}): {action}")
                print(f"    ann_text was : {ann_text}")
                print(f"    ann_text now : {extracted_direct.strip()}")
                updated_line = (
                    f"{ann_id}\t{ann_type} {span_str}\t{extracted_direct.strip()}\n"
                )
                new_lines.append(updated_line)
                fixed_text_only.append(ann_id)
            continue

        # ------------------------------------------------------------------ #
        # DISCONTINUOUS SPAN — adjust boundaries and update ann_text          #
        # ------------------------------------------------------------------ #
        if is_discontinuous:
            new_span_str, actual_text = try_fix_discontinuous_span(
                txt, ann_text, span_str
            )

            if new_span_str is None:
                unfixable.append((ann_id, span_str, ann_text, extracted_direct))
                new_lines.append(raw)
                continue

            if new_span_str == span_str and actual_text.strip() == ann_text.strip():
                already_ok.append(ann_id)
                new_lines.append(raw)
                continue

            action = "would fix span" if args.dry_run else "fixed span"
            print(f"  {ann_id} ({ann_type}): {action}")
            if new_span_str != span_str:
                print(f"    span was     : {span_str}")
                print(f"    span now     : {new_span_str}")
            if actual_text.strip() != ann_text.strip():
                print(f"    ann_text was : {ann_text}")
                print(f"    ann_text now : {actual_text.strip()}")
            updated_line = (
                f"{ann_id}\t{ann_type} {new_span_str}\t{actual_text.strip()}\n"
            )
            new_lines.append(updated_line)
            fixed_disc.append((ann_id, span_str, new_span_str))
            continue

        # ------------------------------------------------------------------ #
        # CONTINUOUS SPAN — search for ann_text in .txt and update            #
        # ------------------------------------------------------------------ #
        orig_start = original_start(span_str)
        hits = find_in_txt(txt, ann_text, orig_start)

        if hits:
            best = hits[0]
            new_start = best.start()
            new_end = best.end()
            new_span = f"{new_start} {new_end}"
            actual_text = txt[new_start:new_end]

            if len(hits) > 1:
                print(f"  {ann_id}: text found {len(hits)} times — using closest to "
                      f"original (orig start {orig_start}, chosen {new_start})")

            action = "would fix span" if args.dry_run else "fixed span"
            print(f"  {ann_id} ({ann_type}): {action}  {span_str}  ->  {new_span}")
            if actual_text.strip() != ann_text.strip():
                print(f"    ann_text was : {ann_text}")
                print(f"    ann_text now : {actual_text.strip()}")

            updated_line = f"{ann_id}\t{ann_type} {new_span}\t{actual_text}\n"
            new_lines.append(updated_line)
            fixed_span.append((ann_id, span_str, new_span))
            continue

        # ------------------------------------------------------------------ #
        # FUZZY FALLBACK — edit distance < 5                                  #
        # ------------------------------------------------------------------ #
        fuzzy_hits = find_in_txt_fuzzy(txt, ann_text, orig_start, max_dist=4)

        if not fuzzy_hits:
            unfixable.append((ann_id, span_str, ann_text, extracted_direct))
            new_lines.append(raw)
            continue

        new_start, new_end, dist, actual_text = fuzzy_hits[0]
        new_span = f"{new_start} {new_end}"

        if len(fuzzy_hits) > 1:
            print(f"  {ann_id}: {len(fuzzy_hits)} fuzzy candidates — using closest "
                  f"(edit dist {dist}, orig start {orig_start}, chosen {new_start})")

        action = "would fix span (fuzzy)" if args.dry_run else "fixed span (fuzzy)"
        print(f"  {ann_id} ({ann_type}): {action}  {span_str}  ->  {new_span}  "
              f"[edit dist {dist}]")
        print(f"    ann_text was : {ann_text}")
        print(f"    ann_text now : {actual_text}")

        updated_line = f"{ann_id}\t{ann_type} {new_span}\t{actual_text}\n"
        new_lines.append(updated_line)
        fixed_fuzzy.append((ann_id, span_str, new_span, dist))

    if not args.dry_run and (fixed_span or fixed_fuzzy or fixed_disc or fixed_text_only):
        ann_path.write_text("".join(new_lines), encoding="utf-8")

    if unfixable:
        print(f"\nTruly unfixable — {len(unfixable)} component(s):")
        for ann_id, span_str, ann_text, extracted in unfixable:
            frags = span_str.count(";") + 1
            print(f"  {ann_id}  ({frags} fragment(s))  span: {span_str}")
            print(f"    ann_text : {ann_text}")
            print(f"    extracted: {extracted}")

    print(f"\nDone.")
    print(f"  Continuous spans fixed (punct-insensitive)         : {len(fixed_span)}")
    print(f"  Continuous spans fixed (edit-distance fallback)    : {len(fixed_fuzzy)}")
    print(f"  Discontinuous spans fixed (boundaries nudged)      : {len(fixed_disc)}")
    print(f"  Ann_text updated (span correct, punct difference)  : {len(fixed_text_only)}")
    print(f"  Already correct                                    : {len(already_ok)}")
    print(f"  Truly unfixable                                    : {len(unfixable)}")


if __name__ == "__main__":
    main()
