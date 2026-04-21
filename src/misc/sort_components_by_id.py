"""
sort_components_by_id.py

Sorts the component (T-) annotations in brat .ann files by their numeric id.
Relation (R-) lines and any other lines are preserved unchanged after the
sorted T-block.

The IDs themselves are never modified — only the order of lines changes.

Usage
-----
    # Sort every .ann file in a folder
    python sort_components_by_id.py --folder /path/to/folder

    # Sort a single file
    python sort_components_by_id.py --file /path/to/file.ann

    # Preview without writing
    python sort_components_by_id.py --folder /path/to/folder --dry-run
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def t_sort_key(line: str) -> int:
    """
    Extract the numeric part of a T-annotation id for sorting.
    e.g.  'T13\tClaim ...'  ->  13
    Falls back to 0 if no number is found (keeps the line stable).
    """
    match = re.match(r"^T(\d+)\t", line)
    return int(match.group(1)) if match else 0


def sort_file(filepath: Path, dry_run: bool) -> bool:
    """
    Read *filepath*, sort its T-lines by numeric id, write back.
    Returns True if the file content changed (or would change).
    """
    original_text = filepath.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)

    t_lines = [l for l in lines if l.startswith("T")]
    other_lines = [l for l in lines if not l.startswith("T")]  # R-lines, blanks, etc.

    sorted_t = sorted(t_lines, key=t_sort_key)

    # Reconstruct: sorted T-block first, then everything else
    new_lines = sorted_t + other_lines
    new_text = "".join(new_lines)

    changed = new_text != original_text

    if changed and not dry_run:
        filepath.write_text(new_text, encoding="utf-8")

    return changed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sort T-annotation lines in brat .ann files by numeric id."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder", "-f",
                       help="Folder containing .ann files to sort.")
    group.add_argument("--file",
                       help="Single .ann file to sort.")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Report what would change without writing files.")
    args = parser.parse_args()

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

    changed_count = 0
    for fp in files:
        changed = sort_file(fp, dry_run=args.dry_run)
        if changed:
            action = "would sort" if args.dry_run else "sorted"
            print(f"  {fp.name}: {action}")
            changed_count += 1
        else:
            print(f"  {fp.name}: already sorted")

    print(f"\nDone. {changed_count}/{len(files)} file(s) "
          f"{'would be ' if args.dry_run else ''}updated.")


if __name__ == "__main__":
    main()
