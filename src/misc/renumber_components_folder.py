"""
renumber_components_folder.py

Renumbers all component (T-) annotations across every .ann file in a folder
**sequentially**, so the counter never resets between files.

Files are processed in sorted (alphabetical) order.  Within each file,
components are renumbered in the order they appear (run sort_components_by_id.py
first if you want numeric order inside each file).

All Arg1 / Arg2 references in relation (R-) lines are updated to match the
new ids.  Spans and text are left untouched.

Usage
-----
    # Renumber all .ann files in a folder starting from 500
    python renumber_components_folder.py --folder /path/to/folder --start 500

    # Preview without writing
    python renumber_components_folder.py --folder /path/to/folder --start 500 --dry-run

Example
-------
  Folder contains file_1.ann (5 components) and file_2.ann (3 components).
  With --start 500:
    file_1.ann  ->  T500 … T504
    file_2.ann  ->  T505 … T507
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Core logic (shared with renumber_components.py)
# ---------------------------------------------------------------------------

def apply_id_map(lines: list[str], id_map: dict[str, str]) -> list[str]:
    """
    Apply *id_map* (old_id -> new_id) to a list of raw brat annotation lines.

    - T-lines : replace the first tab-delimited field (the id itself).
    - R-lines : replace every  :old_id  followed by whitespace or end-of-line
                (covers Arg1:T13, Arg2:T13, etc.).
    - Other lines are passed through unchanged.
    """
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


def renumber_file(filepath: Path, start: int, dry_run: bool) -> dict:
    """
    Renumber all T-annotations in *filepath* starting from *start*.

    Returns a dict with:
        id_map    – dict of old_id -> new_id  (empty when nothing changed)
        count     – number of T-annotations found (0 if none)
        unchanged – True when no ids actually needed to change
        next      – the next free id after this file (start + count)
    """
    original_text = filepath.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)

    # Collect T-line ids in file order
    t_ids_in_order = []
    for line in lines:
        if line.startswith("T"):
            parts = line.split("\t", 2)
            if parts:
                t_ids_in_order.append(parts[0].strip())

    count = len(t_ids_in_order)

    if count == 0:
        return {"id_map": {}, "count": 0, "unchanged": True, "next": start}

    # Build old_id -> new_id mapping
    id_map: dict[str, str] = {}
    for idx, old_id in enumerate(t_ids_in_order):
        new_id = f"T{start + idx}"
        if old_id != new_id:
            id_map[old_id] = new_id

    next_start = start + count

    if not id_map:
        return {"id_map": {}, "count": count, "unchanged": True, "next": next_start}

    # Two-phase rename to avoid mid-rename collisions
    # Phase 1: all old ids -> unique temporary ids
    temp_map: dict[str, str] = {}
    final_map: dict[str, str] = {}
    for i, (old_id, new_id) in enumerate(id_map.items()):
        tmp = f"TTEMP{i}"
        temp_map[old_id] = tmp
        final_map[tmp] = new_id

    new_lines = apply_id_map(lines, temp_map)
    new_lines = apply_id_map(new_lines, final_map)

    if not dry_run:
        filepath.write_text("".join(new_lines), encoding="utf-8")

    return {"id_map": id_map, "count": count, "unchanged": False, "next": next_start}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Renumber T-annotation ids across all .ann files in a folder "
            "sequentially, so the counter carries over from one file to the next."
        )
    )
    parser.add_argument("--folder", "-f", required=True,
                        help="Folder containing .ann files to renumber.")
    parser.add_argument("--start", "-s", type=int, required=True,
                        help="First id number to assign (e.g. 500 -> T500, T501, …).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would change without writing files.")
    args = parser.parse_args()

    if args.start < 0:
        sys.exit("ERROR: --start must be a non-negative integer.")

    target_dir = Path(args.folder)
    if not target_dir.is_dir():
        sys.exit(f"ERROR: not a directory: {target_dir}")

    files = sorted(target_dir.glob("*.ann"))
    if not files:
        sys.exit(f"No .ann files found in {target_dir}")

    if args.dry_run:
        print("(DRY-RUN — files will NOT be modified)\n")

    current_start = args.start

    for fp in files:
        stats = renumber_file(fp, start=current_start, dry_run=args.dry_run)

        if stats["count"] == 0:
            print(f"  {fp.name}: no T-annotations found — skipped")
        elif stats["unchanged"]:
            end_id = current_start + stats["count"] - 1
            print(
                f"  {fp.name}: already numbered T{current_start}…T{end_id} "
                f"({stats['count']} component(s)) — no changes"
            )
        else:
            end_id = current_start + stats["count"] - 1
            action = "would renumber" if args.dry_run else "renumbered"
            print(
                f"  {fp.name}: {action} {len(stats['id_map'])} component(s) "
                f"-> T{current_start}…T{end_id}"
            )
            for old_id, new_id in stats["id_map"].items():
                print(f"    {old_id}  ->  {new_id}")

        # Advance the counter whether or not changes were needed
        current_start = stats["next"]

    print(f"\nDone. Next free id: T{current_start}")


if __name__ == "__main__":
    main()
