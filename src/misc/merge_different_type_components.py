"""
merge_different_type_components.py

For every component in ORIGINAL_FILE(s), find a "similar-but-different-type"
counterpart in PATH_ANNOTATIONS:

  - Similar  : edit distance between texts < --max-distance (default 5)
  - Different: the two components have a different Type

For each matched component in the original file:
  1. Update its span to match the one in PATH_ANNOTATIONS.
  2. Assign it a brand-new id, continuing from the highest id already used in
     PATH_ANNOTATIONS (e.g. if max is T537 the first new id is T538).
     All Arg1/Arg2 references in the original file's R-lines are updated too.
  3. Copy the updated component into PATH_ANNOTATIONS.

If two PATH_ANNOTATIONS components are equally close to the same original
component (tie), the remap is skipped and a warning is printed.
Each PATH_ANNOTATIONS component is matched to at most one original component
(first-come, first-served in file order).

Usage
-----
    # Single file
    python merge_different_type_components.py \\
        --file   /path/to/original.ann \\
        --ann    /path/to/reference.ann \\
        [--max-distance 5] [--dry-run]

    # Whole folder
    python merge_different_type_components.py \\
        --folder /path/to/original/folder \\
        --ann    /path/to/reference.ann \\
        [--max-distance 5] [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Brat parsing helpers
# ---------------------------------------------------------------------------

def parse_t_line(raw: str):
    """
    Parse a T-annotation line.
    Returns (ann_id, ann_type, span_str, ann_text) or None.

    Format: T<id> TAB <type> <span> TAB <text>
    The span_str is everything between the type token and the tab
    (handles discontinuous spans like "100 150;200 250").
    """
    line = raw.rstrip("\n")
    if not line.startswith("T"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return None
    ann_id = parts[0].strip()
    type_and_span = parts[1].strip()
    ann_text = parts[2].strip()
    tokens = type_and_span.split(None, 1)  # split on first whitespace
    ann_type = tokens[0]
    span_str = tokens[1] if len(tokens) > 1 else ""
    return ann_id, ann_type, span_str, ann_text


def max_t_id(filepath: Path) -> int:
    """Return the highest numeric T-id in *filepath*, or 0 if none found."""
    highest = 0
    with open(filepath, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^T(\d+)\t", line)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest


# ---------------------------------------------------------------------------
# Edit distance
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str, max_dist: int = None) -> int:
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a > len_b:
        a, b = b, a
        len_a, len_b = len_b, len_a
    if max_dist is not None and (len_b - len_a) > max_dist:
        return max_dist + 1
    prev = list(range(len_a + 1))
    for j in range(1, len_b + 1):
        curr = [j] + [0] * len_a
        for i in range(1, len_a + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(prev[i] + 1, curr[i - 1] + 1, prev[i - 1] + cost)
        if max_dist is not None and min(curr) > max_dist:
            return max_dist + 1
        prev = curr
    return prev[len_a]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def find_best_different_type_match(ann_type: str, ann_text: str,
                                   ref_components: list,
                                   used_ref_ids: set,
                                   max_dist: int):
    """
    Search *ref_components* for the best match to (ann_type, ann_text):
      - edit_distance(ann_text, ref_text) < max_dist
      - ref_type != ann_type   (different type is required)
      - ref_id not already claimed by another original component

    Returns (ref_id, ref_type, ref_span, ref_text, dist) or
            (None, None, None, None, None) if no suitable match exists.

    Raises a 'tie' signal (returns all-None with dist=-1) when two candidates
    share the same minimum distance.
    """
    best_dist = max_dist  # strictly less than max_dist
    best = None
    ambiguous = False

    for ref_id, ref_type, ref_span, ref_text in ref_components:
        if ref_type == ann_type:  # same type → handled by other scripts
            continue
        if ref_id in used_ref_ids:  # already claimed
            continue
        d = levenshtein(ann_text, ref_text, max_dist=max_dist - 1)
        if d < max_dist:
            if best is None or d < best_dist:
                best_dist = d
                best = (ref_id, ref_type, ref_span, ref_text, d)
                ambiguous = False
            elif d == best_dist:
                ambiguous = True

    if ambiguous:
        return None, None, None, None, -1  # tie signal
    if best is None:
        return None, None, None, None, None
    return best


# ---------------------------------------------------------------------------
# ID remapping (reused from other scripts)
# ---------------------------------------------------------------------------

def apply_id_map(lines: list, id_map: dict) -> list:
    if not id_map:
        return lines
    r_patterns = {
        old: re.compile(r"(?<=:)" + re.escape(old) + r"(?=\s|$)")
        for old in id_map
    }
    result = []
    for raw in lines:
        line = raw.rstrip("\n")
        eol = "\n" if raw.endswith("\n") else ""
        if line.startswith("T"):
            parts = line.split("\t", 2)
            if parts and parts[0].strip() in id_map:
                parts[0] = id_map[parts[0].strip()]
                line = "\t".join(parts)
        elif line.startswith("R"):
            for old_id, pat in r_patterns.items():
                line = pat.sub(id_map[old_id], line)
        result.append(line + eol)
    return result


def build_updated_t_line(new_id: str, orig_type: str,
                         ref_span: str, orig_text: str) -> str:
    return f"{new_id}\t{orig_type} {ref_span}\t{orig_text}\n"


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_file(orig_path: Path, ref_path: Path,
                 max_dist: int, next_id: int, dry_run: bool) -> dict:
    """
    Process one original file against PATH_ANNOTATIONS.

    Returns:
        matches   – list of match info dicts
        next_id   – updated counter (for chaining across multiple files)
    """
    orig_lines = orig_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # Parse all reference components once
    ref_components = []
    with open(ref_path, encoding="utf-8") as fh:
        for raw in fh:
            parsed = parse_t_line(raw)
            if parsed is not None:
                ref_components.append(parsed)  # (id, type, span, text)

    used_ref_ids: set = set()
    id_map: dict = {}  # old_orig_id -> new_id
    new_t_lines: list = []  # lines to append to PATH_ANNOTATIONS
    matches = []

    for raw in orig_lines:
        parsed = parse_t_line(raw)
        if parsed is None:
            continue
        orig_id, orig_type, orig_span, orig_text = parsed

        result = find_best_different_type_match(
            orig_type, orig_text, ref_components, used_ref_ids, max_dist
        )
        ref_id, ref_type, ref_span, ref_text, dist = result

        if dist is None:
            continue  # no match within threshold
        if dist == -1:
            matches.append({
                "status": "ambiguous",
                "orig_id": orig_id,
                "orig_type": orig_type,
                "orig_text": orig_text,
            })
            continue

        # Assign new id
        new_id = f"T{next_id}"
        next_id += 1
        used_ref_ids.add(ref_id)

        id_map[orig_id] = new_id
        new_line = build_updated_t_line(new_id, orig_type, ref_span, orig_text)
        new_t_lines.append(new_line)

        matches.append({
            "status": "matched",
            "orig_id": orig_id,
            "new_id": new_id,
            "orig_type": orig_type,
            "ref_type": ref_type,
            "orig_span": orig_span,
            "ref_span": ref_span,
            "orig_text": orig_text,
            "ref_text": ref_text,
            "dist": dist,
        })

    if not dry_run and id_map:
        # 1+2: update spans and ids in the original file (two-phase rename).
        # The two phases are needed so R-line references to the old T-ids also
        # get rewritten to the new T-ids (via the TTEMP intermediary, which
        # avoids any collision with ids already present in the file).
        temp_map = {old: f"TTEMP{i}" for i, old in enumerate(id_map)}
        final_map = {f"TTEMP{i}": id_map[old] for i, old in enumerate(id_map)}

        # Also update the span for each matched component
        span_updates = {m["orig_id"]: (m["new_id"], m["orig_type"], m["ref_span"], m["orig_text"])
                        for m in matches if m["status"] == "matched"}

        # Step A: rewrite matched T-lines with the updated span, but keep the
        # ORIGINAL id for now, so that apply_id_map's R-line rewriting (which
        # keys off the original ids) still fires in phase 1.
        rewritten_lines = []
        for raw in orig_lines:
            parsed = parse_t_line(raw)
            if parsed is not None:
                orig_id = parsed[0]
                if orig_id in span_updates:
                    _, ntype, nspan, ntext = span_updates[orig_id]
                    rewritten_lines.append(f"{orig_id}\t{ntype} {nspan}\t{ntext}\n")
                    continue
            rewritten_lines.append(raw)

        # Phase 1: remap orig T-ids -> TTEMP ids on BOTH T-lines and R-lines.
        phase1_lines = apply_id_map(rewritten_lines, temp_map)
        # Phase 2: remap TTEMP ids -> final new T-ids on BOTH T-lines and R-lines.
        updated_lines = apply_id_map(phase1_lines, final_map)
        orig_path.write_text("".join(updated_lines), encoding="utf-8")

        # 3: append new components to PATH_ANNOTATIONS
        with open(ref_path, "a", encoding="utf-8") as fh:
            for line in new_t_lines:
                fh.write(line)

    return {"matches": matches, "next_id": next_id}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Find similar-but-different-type components, update their spans and ids, "
                    "and copy them into PATH_ANNOTATIONS."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Single original .ann file.")
    group.add_argument("--folder", "-f", help="Folder of original .ann files.")
    parser.add_argument("--ann", "-a", required=True,
                        help="Reference annotation file (PATH_ANNOTATIONS).")
    parser.add_argument("--max-distance", "-d", type=int, default=5,
                        help="Edit distance threshold (default 5; match requires dist < threshold).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show matches without modifying any file.")
    args = parser.parse_args()

    ann_path = Path(args.ann)
    if not ann_path.is_file():
        sys.exit(f"ERROR: annotation file not found: {ann_path}")

    if args.file:
        fp = Path(args.file)
        if not fp.is_file():
            sys.exit(f"ERROR: file not found: {fp}")
        files = [fp]
    else:
        folder = Path(args.folder)
        if not folder.is_dir():
            sys.exit(f"ERROR: folder not found: {folder}")
        files = sorted(folder.glob("*.ann"))
        if not files:
            sys.exit(f"No .ann files found in {folder}")

    # Determine starting id (max existing + 1)
    next_id = max_t_id(ann_path) + 1
    print(f"Reference: {ann_path.name}  (next available id: T{next_id})")
    print(f"Threshold: edit distance < {args.max_distance}")
    if args.dry_run:
        print("(DRY-RUN — no files will be modified)\n")
    else:
        print()

    total_matched = 0
    total_ambiguous = 0

    for fp in files:
        result = process_file(fp, ann_path,
                              max_dist=args.max_distance,
                              next_id=next_id,
                              dry_run=args.dry_run)
        next_id = result["next_id"]
        matches = result["matches"]

        matched = [m for m in matches if m["status"] == "matched"]
        ambiguous = [m for m in matches if m["status"] == "ambiguous"]

        if not matches:
            print(f"  {fp.name}: no similar-but-different-type components found")
            continue

        if matched:
            action = "would update+copy" if args.dry_run else "updated+copied"
            print(f"  {fp.name}: {action} {len(matched)} component(s)")
            for m in matched:
                print(f"    {m['orig_id']} ({m['orig_type']})  ->  "
                      f"{m['new_id']}  [ref was {m['ref_type']}]  (dist={m['dist']})")
                if m["orig_span"] != m["ref_span"]:
                    print(f"      span: {m['orig_span']}  ->  {m['ref_span']}")
                if m["dist"] > 0:
                    print(f"      original : {m['orig_text']}")
                    print(f"      reference: {m['ref_text']}")
            total_matched += len(matched)

        if ambiguous:
            print(f"  {fp.name}: SKIPPED {len(ambiguous)} ambiguous match(es) (tie in edit distance)")
            for m in ambiguous:
                print(f"    {m['orig_id']} ({m['orig_type']}): {m['orig_text'][:60]}")
            total_ambiguous += len(ambiguous)

    print(f"\nDone.")
    print(f"  Components {'that would be ' if args.dry_run else ''}updated+copied : {total_matched}")
    print(f"  Ambiguous matches skipped              : {total_ambiguous}")
    if args.dry_run and total_matched:
        print("\n  Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
