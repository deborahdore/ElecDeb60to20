"""
move_relations.py

Moves every relation (R-) annotation from all .ann files in FOLDER_ORIGINAL
into PATH_ANNOTATIONS, then:
  1. Merges with any R-lines already present in PATH_ANNOTATIONS.
  2. Sorts all R-lines by their numeric id.
  3. Renumbers them consecutively from R1.

R-lines are removed from each source file in FOLDER_ORIGINAL (T-lines and
everything else in those files are left untouched).

Usage
-----
    python move_relations.py \\
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

def r_sort_key(line: str) -> int:
    """
    Extract the numeric part of an R-annotation id for sorting.
    e.g.  'R13\\tSupport ...'  ->  13
    Falls back to 0 if no number is found.
    """
    m = re.match(r"^R(\d+)\t", line.rstrip("\n"))
    return int(m.group(1)) if m else 0


def renumber_r_lines(lines: list[str]) -> list[str]:
    """
    Assign new consecutive R-ids (R1, R2, …) to a list of R-annotation lines,
    preserving the rest of each line verbatim.
    """
    result = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        # Replace the id field (everything before the first TAB)
        rest = line.split("\t", 1)[1] if "\t" in line else line
        result.append(f"R{idx}\t{rest}\n")
    return result


def split_lines(filepath: Path) -> tuple[list[str], list[str]]:
    """
    Read *filepath* and return (non_r_lines, r_lines) preserving order.
    """
    all_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)
    non_r = [l for l in all_lines if not l.startswith("R")]
    r = [l for l in all_lines if l.startswith("R")]
    return non_r, r


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Move R-annotations from FOLDER_ORIGINAL files into PATH_ANNOTATIONS, "
                    "sort by id, and renumber from R1."
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

    # ---- Collect R-lines from each source file --------------------------------
    all_r_lines: list[str] = []
    source_non_r: dict[Path, list[str]] = {}

    for fp in ann_files:
        non_r, r = split_lines(fp)
        source_non_r[fp] = non_r
        all_r_lines.extend(r)
        print(f"  {fp.name}: collected {len(r)} relation(s)")

    print(f"\nTotal relations collected from FOLDER_ORIGINAL: {len(all_r_lines)}")

    # ---- Load existing R-lines from PATH_ANNOTATIONS -------------------------
    ann_non_r, ann_existing_r = split_lines(ann_path)
    if ann_existing_r:
        print(f"Existing relations in {ann_path.name}: {len(ann_existing_r)}")
    else:
        print(f"No existing relations in {ann_path.name}")

    # ---- Merge, sort, renumber -----------------------------------------------
    combined_r = ann_existing_r + all_r_lines
    combined_r.sort(key=r_sort_key)
    renumbered_r = renumber_r_lines(combined_r)

    print(f"Total relations after merge: {len(renumbered_r)}")
    print(f"\nFirst 5 renumbered relations:")
    for line in renumbered_r[:5]:
        print(f"  {line}", end="")
    if len(renumbered_r) > 5:
        print(f"  …")

    # ---- Write changes -------------------------------------------------------
    if not args.dry_run:
        # Write PATH_ANNOTATIONS: existing T-lines + blank separator + R-lines
        # Keep any trailing newline structure clean
        ann_content = "".join(ann_non_r)
        if ann_content and not ann_content.endswith("\n"):
            ann_content += "\n"
        ann_content += "".join(renumbered_r)
        ann_path.write_text(ann_content, encoding="utf-8")
        print(f"\nWrote {len(renumbered_r)} relation(s) to {ann_path.name}")

        # Remove R-lines from each source file
        print("\nSource files updated (R-lines removed):")
        for fp, non_r in source_non_r.items():
            # Count how many R-lines existed before writing
            original_r_count = len([l for l in fp.read_text(encoding="utf-8").splitlines(keepends=True)
                                    if l.startswith("R")])
            fp.write_text("".join(non_r), encoding="utf-8")
            print(f"  {fp.name}: removed {original_r_count} relation(s)")
    else:
        print(f"\n(DRY-RUN) Would write {len(renumbered_r)} relation(s) to {ann_path.name}")
        print(f"(DRY-RUN) Would remove R-lines from {len(ann_files)} source file(s)")

    print("\nDone.")


if __name__ == "__main__":
    main()
