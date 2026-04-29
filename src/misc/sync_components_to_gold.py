"""
sync_components_to_gold.py

For every component (T-annotation) in each .ann file under FOLDER (or a single
--file), find a corresponding component in the gold file (--ann):

  Corresponding = same text, edit distance < --max-distance (default 3),
                  regardless of type, span, or id.

When a match is found the component in the source file is updated to match the
gold exactly:
  - id        → replaced with the gold id
  - type+span → replaced with the gold type+span field
  - text      → replaced with the gold text (if slightly different)

All R-lines in the source file that reference the old id are updated to use
the new id.

A component is also updated when its id already equals the gold id but its
span, type, or text differs — in that case only those fields are rewritten.

Tie handling: if two gold components are equally close to the same source
component the remap is skipped and a warning is printed.

Each gold component is matched to at most one source component (first-come,
first-served in file order).

Conflict handling
-----------------
A remap  old_id -> new_id  is a conflict when new_id is already occupied in
the same file by a different component that is NOT itself being remapped
(so the slot won't be freed).  Conflicting remaps are skipped and reported.
All other remaps are applied atomically via a two-phase temp-id approach that
correctly handles chains and cycles.

Usage
-----
    # Whole folder
    python sync_components_to_gold.py \\
        --folder /path/to/folder \\
        --ann    /path/to/gold.ann \\
        [--max-distance 3] \\
        [--dry-run]

    # Single file
    python sync_components_to_gold.py \\
        --file /path/to/file.ann \\
        --ann  /path/to/gold.ann \\
        [--max-distance 3] \\
        [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_t_line(raw: str):
    """
    Parse a T-annotation line.
    Returns (ann_id, ann_type, type_span_field, ann_text) or None.
    Format: T<id>TAB<type> <start> <end>TAB<text>

    type_span_field is the full second tab-delimited field ("Type start end"),
    preserved verbatim so it can be copied wholesale to the output.
    """
    line = raw.rstrip("\n")
    if not line.startswith("T"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return None
    ann_id = parts[0].strip()
    type_span_field = parts[1].strip()
    ann_type = type_span_field.split()[0]
    ann_text = parts[2].strip()
    return ann_id, ann_type, type_span_field, ann_text


def load_reference(path: Path) -> list:
    """
    Load all T-annotations from the gold file as a flat list:
        [(ann_id, ann_type, type_span_field, ann_text), ...]
    """
    components = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            parsed = parse_t_line(raw)
            if parsed is not None:
                components.append(parsed)
    return components


# ---------------------------------------------------------------------------
# Edit distance
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str, max_dist: int = None) -> int:
    """
    Levenshtein distance between a and b.
    If max_dist is given, returns early with max_dist+1 once the true distance
    is certain to exceed it.
    """
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a > len_b:
        a, b = b, a
        len_a, len_b = len_b, len_a
    if max_dist is not None and (len_b - len_a) >= max_dist:
        return max_dist + 1
    prev = list(range(len_a + 1))
    for j in range(1, len_b + 1):
        curr = [j] + [0] * len_a
        for i in range(1, len_a + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(
                prev[i] + 1,
                curr[i - 1] + 1,
                prev[i - 1] + cost,
            )
        if max_dist is not None and min(curr) >= max_dist:
            return max_dist + 1
        prev = curr
    return prev[len_a]


def find_best_match(ann_text: str, reference: list,
                    used_gold_ids: set, max_dist: int):
    """
    Search *reference* (flat list) for the gold component whose text has the
    smallest edit distance to *ann_text*, provided distance < max_dist.
    Gold components already claimed by another source component are skipped.

    Returns (gold_id, gold_type_span, gold_text, dist)
         or (None, None, None, None)  — no match within threshold
         or (None, None, None, -1)    — tie (two equally close candidates)
    """
    best_dist = max_dist      # strictly less than
    best = None
    ambiguous = False

    for gold_id, _gold_type, gold_type_span, gold_text in reference:
        if gold_id in used_gold_ids:
            continue
        d = levenshtein(ann_text, gold_text, max_dist=max_dist - 1)
        if d < max_dist:
            if best is None or d < best_dist:
                best_dist = d
                best = (gold_id, gold_type_span, gold_text, d)
                ambiguous = False
            elif d == best_dist:
                ambiguous = True

    if ambiguous:
        return None, None, None, -1
    if best is None:
        return None, None, None, None
    return best


# ---------------------------------------------------------------------------
# ID remapping
# ---------------------------------------------------------------------------

def apply_id_map(lines: list, id_map: dict,
                 t_line_content_update: dict = None) -> list:
    """
    Apply id_map (old_id -> new_id) to brat annotation lines.

    - T-lines: the ID field is replaced.  If t_line_content_update provides
               an entry for the NEW id, the type+span and text fields are
               also overwritten.
    - R-lines: every :old_id occurrence is replaced.
    - Other lines: passed through unchanged.

    t_line_content_update maps  new_id -> (type_span_field, text).
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
                new_id = id_map[parts[0].strip()]
                parts[0] = new_id
                if (t_line_content_update is not None
                        and new_id in t_line_content_update
                        and len(parts) >= 3):
                    new_type_span, new_text = t_line_content_update[new_id]
                    parts[1] = new_type_span
                    parts[2] = new_text
                line = "\t".join(parts)

        elif line.startswith("R"):
            for old_id, pat in r_patterns.items():
                line = pat.sub(id_map[old_id], line)

        result.append(line + eol)
    return result


def build_temp_id(index: int) -> str:
    return f"TTEMP{index}"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_remaps(filepath: Path, reference: list, max_dist: int) -> dict:
    """
    Scan filepath and return all proposed remaps without touching the file.

    Returns a dict:
        proposed     – list of (old_id, new_id, dist,
                                orig_text, gold_text,
                                orig_type_span, gold_type_span)
        conflicts    – list of (old_id, new_id)
        ambiguous    – list of old_ids where two gold entries tied
        existing_ids – set of all T-ids currently in the file
    """
    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

    full_remap: dict = {}       # old_id -> new_id
    remap_meta: dict = {}       # old_id -> (dist, orig_text, gold_text,
                                #            orig_type_span, gold_type_span)
    existing_ids: set = set()
    ambiguous_ids: list = []
    used_gold_ids: set = set()  # gold ids already claimed by an earlier component

    for raw in original_lines:
        parsed = parse_t_line(raw)
        if parsed is None:
            continue
        old_id, _ann_type, orig_type_span, ann_text = parsed
        existing_ids.add(old_id)

        gold_id, gold_type_span, gold_text, dist = find_best_match(
            ann_text, reference, used_gold_ids, max_dist
        )

        if dist == -1:
            ambiguous_ids.append(old_id)
            continue
        if dist is None:
            continue  # no match within threshold

        used_gold_ids.add(gold_id)

        # Propose an update if ANY of id / type+span / text differs
        if (old_id != gold_id
                or orig_type_span != gold_type_span
                or ann_text != gold_text):
            full_remap[old_id] = gold_id
            remap_meta[old_id] = (dist, ann_text, gold_text,
                                  orig_type_span, gold_type_span)

    # Detect conflicts (only when the id actually changes)
    conflict_olds: set = set()
    for old_id, new_id in full_remap.items():
        if old_id == new_id:
            continue
        if new_id in existing_ids and new_id not in full_remap:
            conflict_olds.add(old_id)

    proposed = [
        (k, full_remap[k], *remap_meta[k])
        for k in full_remap
        if k not in conflict_olds
    ]
    conflicts = [(k, full_remap[k]) for k in conflict_olds]

    return {
        "proposed": proposed,
        "conflicts": conflicts,
        "ambiguous": ambiguous_ids,
        "existing_ids": existing_ids,
    }


def apply_remaps(filepath: Path, approved: list) -> int:
    """
    Apply an approved list of remaps to filepath and write it back.

    approved is a list of:
        (old_id, new_id, dist, orig_text, gold_text, orig_type_span, gold_type_span)

    Uses a two-phase temp-id rename to safely handle chains and cycles.
    Returns the number of components updated.
    """
    if not approved:
        return 0

    effective_remap: dict = {}
    content_update: dict = {}   # new_id -> (type_span, text)
    for entry in approved:
        old_id, new_id, _dist, _orig_text, gold_text, _orig_span, gold_span = entry
        effective_remap[old_id] = new_id
        content_update[new_id] = (gold_span, gold_text)

    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

    temp_map: dict = {}
    final_map: dict = {}
    for idx, (old_id, new_id) in enumerate(effective_remap.items()):
        tmp = build_temp_id(idx)
        temp_map[old_id] = tmp
        final_map[tmp] = new_id

    lines = apply_id_map(original_lines, temp_map)
    lines = apply_id_map(lines, final_map, t_line_content_update=content_update)
    filepath.write_text("".join(lines), encoding="utf-8")
    return len(effective_remap)


# ---------------------------------------------------------------------------
# Interactive dry-run
# ---------------------------------------------------------------------------

def ask_user(old_id, new_id, dist, orig_text, gold_text,
             orig_span, gold_span) -> str:
    if old_id == new_id:
        print(f"\n  {old_id}  (id unchanged — type/span/text update, dist={dist})")
    else:
        print(f"\n  {old_id}  ->  {new_id}  (dist={dist})")
    if orig_span != gold_span:
        print(f"    original type+span : {orig_span}")
        print(f"    gold     type+span : {gold_span}")
    if dist > 0:
        print(f"    original text : {orig_text}")
        print(f"    gold text     : {gold_text}")
    while True:
        try:
            ans = input("  Apply? [y]es / [n]o / [a]ll / [q]uit all: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 'q'
        if ans in ('y', 'n', 'a', 'q'):
            return ans
        print("  Please enter y, n, a, or q.")


def interactive_filter(proposed: list, filename: str):
    approved, rejected = [], []
    auto_approve = False
    print(f"\n--- {filename}: {len(proposed)} proposed remap(s) ---")
    for entry in proposed:
        old_id, new_id, dist, orig_text, gold_text, orig_span, gold_span = entry
        if auto_approve:
            approved.append(entry)
            print(f"  {old_id}  ->  {new_id}  (dist={dist})  [auto-approved]")
            continue
        ans = ask_user(old_id, new_id, dist, orig_text, gold_text,
                       orig_span, gold_span)
        if ans == 'y':
            approved.append(entry)
        elif ans == 'n':
            rejected.append(entry)
        elif ans == 'a':
            approved.append(entry)
            auto_approve = True
            print("  (approving all remaining remaps for this file)")
        elif ans == 'q':
            rejected.append(entry)
            idx = proposed.index(entry)
            rejected.extend(proposed[idx + 1:])
            print("  (rejecting all remaining remaps for this file)")
            break
    return approved, rejected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sync source .ann components to a gold annotation file.\n\n"
            "For each source component, finds the gold component with the "
            "closest text (edit distance < --max-distance, default 3), "
            "regardless of type. Updates the source component's id, type, "
            "span, and text to match the gold exactly.\n\n"
            "With --dry-run, each proposed change is shown interactively."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--folder", "-f",
                              help="Folder of source .ann files.")
    source_group.add_argument("--file",
                              help="Single source .ann file.")
    parser.add_argument("--ann", "-a", required=True,
                        help="Gold annotation file.")
    parser.add_argument("--max-distance", "-d", type=int, default=3,
                        help="Edit distance threshold — match requires dist < this value (default: 3).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Review each proposed change interactively. "
                             "Approved changes are written to disk; rejected ones are skipped.")
    args = parser.parse_args()

    if args.max_distance < 1:
        sys.exit("ERROR: --max-distance must be >= 1.")

    ann_path = Path(args.ann)
    if not ann_path.is_file():
        sys.exit(f"ERROR: gold file not found: {ann_path}")

    if args.file:
        src_path = Path(args.file)
        if not src_path.is_file():
            sys.exit(f"ERROR: file not found: {src_path}")
        ann_files = [src_path]
    else:
        folder = Path(args.folder)
        if not folder.is_dir():
            sys.exit(f"ERROR: folder not found: {folder}")
        ann_files = sorted(folder.glob("*.ann"))
        if not ann_files:
            sys.exit(f"No .ann files found in {folder}")

    reference = load_reference(ann_path)
    print(f"Gold loaded  : {len(reference)} component(s) from {ann_path.name}")
    print(f"Threshold    : edit distance < {args.max_distance}")
    print(f"Source files : {len(ann_files)}")
    if args.dry_run:
        print("Mode         : INTERACTIVE (approved changes are written to disk)")
        print("               [y]es / [n]o / [a]ll / [q]uit\n")
    else:
        print()

    total_remapped = 0
    total_rejected = 0
    total_conflicts = 0
    total_ambiguous = 0

    for fp in ann_files:
        result = compute_remaps(fp, reference, max_dist=args.max_distance)

        nothing = (not result["proposed"]
                   and not result["conflicts"]
                   and not result["ambiguous"])
        if nothing:
            print(f"  {fp.name}: no matching gold components found")
            continue

        if args.dry_run:
            if result["proposed"]:
                approved, rejected = interactive_filter(result["proposed"], fp.name)
            else:
                approved, rejected = [], []

            if approved:
                n = apply_remaps(fp, approved)
                print(f"  {fp.name}: applied {n} update(s)")
            if rejected:
                print(f"  {fp.name}: skipped {len(rejected)} update(s)")
            total_remapped += len(approved)
            total_rejected += len(rejected)

        else:
            n = apply_remaps(fp, result["proposed"])
            print(f"  {fp.name}: updated {n} component(s)")
            total_remapped += n

        if result["conflicts"]:
            print(f"  {fp.name}: SKIPPED {len(result['conflicts'])} conflict(s) "
                  f"(target id already occupied by a different component)")
            for old_id, new_id in result["conflicts"]:
                print(f"    {old_id}  ->  {new_id}  [CONFLICT — {new_id} already exists]")
            total_conflicts += len(result["conflicts"])

        if result["ambiguous"]:
            print(f"  {fp.name}: SKIPPED {len(result['ambiguous'])} ambiguous match(es) "
                  f"(two gold components equally close)")
            for old_id in result["ambiguous"]:
                print(f"    {old_id}  [AMBIGUOUS]")
            total_ambiguous += len(result["ambiguous"])

    print(f"\nDone.")
    if args.dry_run:
        print(f"  Applied (approved) : {total_remapped}")
        print(f"  Skipped (rejected) : {total_rejected}")
    else:
        print(f"  Components updated : {total_remapped}")
    print(f"  Conflicts skipped  : {total_conflicts}")
    print(f"  Ambiguous skipped  : {total_ambiguous}")
    if total_conflicts:
        print("  NOTE: conflicting remaps were skipped — resolve manually if needed.")
    if total_ambiguous:
        print("  NOTE: ambiguous remaps were skipped — lower --max-distance or resolve manually.")


if __name__ == "__main__":
    main()
