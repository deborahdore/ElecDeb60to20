"""
remove_duplicate_components.py

For each brat .ann file in FOLDER_ORIGINAL, removes component (T-) annotations
that are also present in PATH_ANNOTATIONS.

Matching criteria (span is always ignored):
  - same id
  - same type
  - edit distance between texts <= --max-distance  (default 2)

A max-distance of 0 reproduces the original exact-text behaviour.

Relation (R-) annotations are never touched.

Usage:
    python remove_duplicate_components.py \
        --folder  /path/to/original/folder \
        --ann     /path/to/reference.ann \
        [--max-distance 2] \
        [--dry-run]
"""

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_component_line(line: str):
    """
    Parse a brat text-bound (T) annotation line.
    Returns (ann_id, ann_type, ann_text) or None.
    """
    line = line.rstrip("\n")
    if not line.startswith("T"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return None
    ann_id = parts[0].strip()
    ann_type = parts[1].strip().split()[0]
    ann_text = parts[2].strip()
    return ann_id, ann_type, ann_text


def load_reference_annotations(path: Path) -> dict:
    """
    Build  (id, type) -> [text, ...]  from PATH_ANNOTATIONS.
    Multiple texts per (id, type) key are supported (edge case).
    Only T-lines are considered.
    """
    refs: dict[tuple, list[str]] = {}
    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            parsed = parse_component_line(raw_line)
            if parsed is not None:
                ann_id, ann_type, ann_text = parsed
                refs.setdefault((ann_id, ann_type), []).append(ann_text)
    return refs


# ---------------------------------------------------------------------------
# Edit distance
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str, max_dist: int = None) -> int:
    """
    Levenshtein distance between *a* and *b*, with optional early exit.
    Returns max_dist + 1 as soon as the distance is certain to exceed max_dist.
    """
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


def matches_reference(ann_id: str, ann_type: str, ann_text: str,
                      reference: dict, max_dist: int) -> tuple:
    """
    Return (True, ref_text, dist) if the component matches any entry in
    *reference* within the edit-distance threshold, else (False, None, None).

    Matching: exact (id, type) key, then fuzzy text.
    The closest reference text is chosen; exact matches (dist=0) short-circuit.
    """
    candidates = reference.get((ann_id, ann_type), [])
    best_dist = max_dist + 1
    best_text = None
    for ref_text in candidates:
        d = levenshtein(ann_text, ref_text, max_dist=max_dist)
        if d < best_dist:
            best_dist = d
            best_text = ref_text
            if d == 0:
                break  # can't do better
    if best_dist <= max_dist:
        return True, best_text, best_dist
    return False, None, None


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def filter_file(filepath: Path, reference: dict, max_dist: int, dry_run: bool) -> dict:
    """
    Remove from *filepath* any T-annotation that matches a reference entry
    (same id, same type, text within edit-distance threshold).
    R-annotations and all other lines are kept unchanged.

    Returns a stats dict with 'removed_entries': list of
        (original_line, ref_text, dist)
    """
    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)
    kept_lines = []
    removed_entries = []

    for raw_line in original_lines:
        stripped = raw_line.rstrip("\n")

        if stripped.startswith("T"):
            parsed = parse_component_line(raw_line)
            if parsed is not None:
                ann_id, ann_type, ann_text = parsed
                matched, ref_text, dist = matches_reference(
                    ann_id, ann_type, ann_text, reference, max_dist
                )
                if matched:
                    removed_entries.append((stripped, ref_text, dist))
                    continue  # drop this line

        kept_lines.append(raw_line)

    if not dry_run and removed_entries:
        filepath.write_text("".join(kept_lines), encoding="utf-8")

    return {
        "total": len(original_lines),
        "removed": len(removed_entries),
        "kept": len(kept_lines),
        "removed_entries": removed_entries,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Remove duplicate component annotations from brat files using fuzzy text matching."
    )
    parser.add_argument("--folder", "-f", required=True,
                        help="Folder containing the original brat .ann files (FOLDER_ORIGINAL).")
    parser.add_argument("--ann", "-a", required=True,
                        help="Reference annotation file (PATH_ANNOTATIONS).")
    parser.add_argument("--max-distance", "-d", type=int, default=5,
                        help="Maximum edit distance to consider texts equivalent (default: 2). "
                             "Use 0 for exact matching.")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Print what would be removed without modifying any file.")
    args = parser.parse_args()

    if args.max_distance < 0:
        sys.exit("ERROR: --max-distance must be >= 0.")

    folder = Path(args.folder)
    ann_path = Path(args.ann)

    if not folder.is_dir():
        sys.exit(f"ERROR: folder not found or not a directory: {folder}")
    if not ann_path.is_file():
        sys.exit(f"ERROR: annotation file not found: {ann_path}")

    reference = load_reference_annotations(ann_path)
    total_ref = sum(len(v) for v in reference.values())
    print(f"Reference annotations loaded: {total_ref} component(s) from {ann_path.name}")
    print(f"Similarity threshold: edit distance <= {args.max_distance}")

    if not reference:
        print("No component annotations found in reference file — nothing to remove.")
        return

    ann_files = sorted(folder.glob("*.ann"))
    if not ann_files:
        print(f"No .ann files found in {folder}")
        return

    print(f"Processing {len(ann_files)} file(s) in {folder} …")
    if args.dry_run:
        print("(DRY-RUN mode — files will NOT be modified)\n")

    total_removed = 0
    for fp in ann_files:
        stats = filter_file(fp, reference, max_dist=args.max_distance, dry_run=args.dry_run)
        if stats["removed"]:
            action = "would remove" if args.dry_run else "removed"
            print(f"  {fp.name}: {action} {stats['removed']} annotation(s)")
            for orig_line, ref_text, dist in stats["removed_entries"]:
                print(f"    - {orig_line}  (dist={dist})")
                if dist > 0:
                    print(f"      reference: {ref_text}")
            total_removed += stats["removed"]
        else:
            print(f"  {fp.name}: no matching annotations found")

    print(f"\nDone. Total annotations {'that would be ' if args.dry_run else ''}removed: {total_removed}")


if __name__ == "__main__":
    main()
