"""
renumber_components.py

Renumbers all component (T-) annotations in a brat .ann file starting from a
given number, incrementing by 1.  Components are renumbered in the order they
appear in the file (run sort_components_by_id.py first if you want numeric
order).  All Arg1 / Arg2 references in relation (R-) lines are updated to
match the new ids.

The span and text of every annotation are left untouched.

Usage
-----
    # Renumber a single file starting from 1
    python renumber_components.py --file /path/to/file.ann --start 1

    # Renumber every .ann file in a folder, each starting from 1
    python renumber_components.py --folder /path/to/folder --start 1

    # Preview without writing
    python renumber_components.py --file /path/to/file.ann --start 100 --dry-run
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Core logic
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

    Returns a stats dict:
        id_map    – dict of old_id -> new_id
        unchanged – True when no ids actually changed
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

    if not t_ids_in_order:
        return {"id_map": {}, "unchanged": True}

    # Build old_id -> new_id mapping
    id_map: dict[str, str] = {}
    for idx, old_id in enumerate(t_ids_in_order):
        new_id = f"T{start + idx}"
        if old_id != new_id:
            id_map[old_id] = new_id

    if not id_map:
        return {"id_map": {}, "unchanged": True}

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

    return {"id_map": id_map, "unchanged": False}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Renumber T-annotation ids in brat .ann files from a given start value."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder", "-f",
                       help="Folder containing .ann files to renumber.")
    group.add_argument("--file",
                       help="Single .ann file to renumber.")
    parser.add_argument("--start", "-s", type=int, required=True,
                        help="First id number to assign (e.g. 1 -> T1, T2, T3 …).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would change without writing files.")
    args = parser.parse_args()

    if args.start < 0:
        sys.exit("ERROR: --start must be a non-negative integer.")

    if args.folder:
        target_dir = Path(args.folder)
        if not target_dir.is_dir():
            sys.exit(f"ERROR: not a directory: {target_dir}")
        files = sorted(target_dir.glob("*.ann"))
        if not files:
            sys.exit(f"No .ann files found in {target_dir}")
    else:
        fp = Path(args.file)
        if not fp.is_file():
            sys.exit(f"ERROR: file not found: {fp}")
        files = [fp]

    if args.dry_run:
        print("(DRY-RUN — files will NOT be modified)\n")

    for fp in files:
        stats = renumber_file(fp, start=args.start, dry_run=args.dry_run)

        if stats["unchanged"]:
            print(f"  {fp.name}: already numbered from T{args.start} — no changes")
            continue

        action = "would renumber" if args.dry_run else "renumbered"
        print(f"  {fp.name}: {action} {len(stats['id_map'])} component(s)")
        for old_id, new_id in stats["id_map"].items():
            print(f"    {old_id}  ->  {new_id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
