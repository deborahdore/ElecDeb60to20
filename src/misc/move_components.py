"""
move_components.py

Moves every component (T-) annotation from all .ann files in FOLDER_ORIGINAL
into PATH_ANNOTATIONS, then:
  1. Merges with any T-lines already present in PATH_ANNOTATIONS.
  2. Sorts all T-lines by their numeric id.
  3. Renumbers them consecutively from T1.

T-lines are removed from each source file in FOLDER_ORIGINAL (R-lines and
everything else in those files are left untouched).

Usage
-----
    python move_components.py \\
        --folder  /path/to/original/folder \\
        --ann     /path/to/reference.ann   \\
        [--dry-run]
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
    e.g.  'T13\\tClaim 10 20\\tsome text'  ->  13
    Falls back to 0 if no number is found.
    """
    m = re.match(r"^T(\d+)\t", line.rstrip("\n"))
    return int(m.group(1)) if m else 0


def renumber_t_lines(lines: list[str]) -> list[str]:
    """
    Assign new consecutive T-ids (T1, T2, …) to a list of T-annotation lines,
    preserving the rest of each line verbatim.
    """
    result = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        # Replace the id field (everything before the first TAB)
        rest = line.split("\t", 1)[1] if "\t" in line else line
        result.append(f"T{idx}\t{rest}\n")
    return result


def split_lines(filepath: Path) -> tuple[list[str], list[str]]:
    """
    Read *filepath* and return (non_t_lines, t_lines) preserving order.
    """
    all_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)
    non_t = [l for l in all_lines if not l.startswith("T")]
    t = [l for l in all_lines if l.startswith("T")]
    return non_t, t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Move T-annotations from FOLDER_ORIGINAL files into PATH_ANNOTATIONS, "
                    "sort by id, and renumber from T1."
    )
    parser.add_argument("--folder", "-f", required=True,
                        help="Folder containing the original brat .ann files (FOLDER_ORIGINAL).")
    parser.add_argument("--ann", "-a", required=True,
                        help="Destination annotation file (PATH_ANNOTATIONS).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would happen without writing any file.")
    args = parser.parse_args()

    folder = Path(args.folder)
    ann_path = Path(args.ann)

    if not folder.is_dir():
        sys.exit(f"ERROR: folder not found: {folder}")
    if not ann_path.is_file():
        sys.exit(f"ERROR: annotation file not found: {ann_path}")

    ann_files = sorted(folder.glob("*.ann"))
    if not ann_files:
        sys.exit(f"No .ann files found in {folder}")

    if args.dry_run:
        print("(DRY-RUN — no files will be modified)\n")

    # ---- Collect T-lines from each source file --------------------------------
    all_t_lines: list[str] = []
    source_non_t: dict[Path, list[str]] = {}

    for fp in ann_files:
        non_t, t = split_lines(fp)
        source_non_t[fp] = non_t
        all_t_lines.extend(t)
        print(f"  {fp.name}: collected {len(t)} component(s)")

    print(f"\nTotal components collected from FOLDER_ORIGINAL: {len(all_t_lines)}")

    # ---- Load existing T-lines from PATH_ANNOTATIONS -------------------------
    ann_non_t, ann_existing_t = split_lines(ann_path)
    if ann_existing_t:
        print(f"Existing components in {ann_path.name}: {len(ann_existing_t)}")
    else:
        print(f"No existing components in {ann_path.name}")

    # ---- Merge, sort, renumber -----------------------------------------------
    combined_t = ann_existing_t + all_t_lines
    combined_t.sort(key=t_sort_key)
    renumbered_t = renumber_t_lines(combined_t)

    print(f"Total components after merge: {len(renumbered_t)}")
    print(f"\nFirst 5 renumbered components:")
    for line in renumbered_t[:5]:
        print(f"  {line}", end="")
    if len(renumbered_t) > 5:
        print(f"  …")

    # ---- Write changes -------------------------------------------------------
    if not args.dry_run:
        # Write PATH_ANNOTATIONS: T-lines first, then any remaining non-T lines
        # Keep any trailing newline structure clean
        t_content = "".join(renumbered_t)
        if t_content and not t_content.endswith("\n"):
            t_content += "\n"
        t_content += "".join(ann_non_t)
        ann_path.write_text(t_content, encoding="utf-8")
        print(f"\nWrote {len(renumbered_t)} component(s) to {ann_path.name}")

        # Remove T-lines from each source file
        print("\nSource files updated (T-lines removed):")
        for fp, non_t in source_non_t.items():
            # Count how many T-lines existed before writing
            original_t_count = len([l for l in fp.read_text(encoding="utf-8").splitlines(keepends=True)
                                    if l.startswith("T")])
            fp.write_text("".join(non_t), encoding="utf-8")
            print(f"  {fp.name}: removed {original_t_count} component(s)")
    else:
        print(f"\n(DRY-RUN) Would write {len(renumbered_t)} component(s) to {ann_path.name}")
        print(f"(DRY-RUN) Would remove T-lines from {len(ann_files)} source file(s)")

    print("\nDone.")


if __name__ == "__main__":
    main()
