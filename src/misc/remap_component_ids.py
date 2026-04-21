"""
remap_component_ids.py

For every component (T-annotation) in each file under FOLDER_ORIGINAL, look for
a "similar" component in PATH_ANNOTATIONS — defined as having the *same Type*
and a text whose edit distance from the original is less than --max-distance
(default 2, i.e. edit distance 0, 1 or 2 are all considered similar).

Example: "Your regulations are a disaster"  ~  "Your regulations are a disaster."
         (one character difference — period at the end)

When a match is found the component's id, span (start/end offsets) and text
are replaced with those from PATH_ANNOTATIONS.  All relation (R-) lines that
reference the old id are updated to use the new id as well.

A component is also updated when its id already equals the reference id but
its span or text differs — in that case only the span/text are rewritten.

If more than one reference component matches (same type, distance within
threshold), the one with the smallest edit distance is chosen; if there is a
tie the remap is skipped and a warning is printed.

Conflict handling
-----------------
A remap  old_id -> new_id  is a **conflict** when new_id is already occupied
in the same file by a *different* component that is NOT itself being remapped
(so the slot won't be freed by any other step).  Conflicting remaps are skipped
and reported; all other remaps are applied atomically via a two-phase
temp-id approach that correctly handles chains and cycles.

Usage
-----
    python remap_component_ids.py \\
        --folder       /path/to/original/folder \\
        --ann          /path/to/reference.ann   \\
        [--max-distance 2]                       \\
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
    Parse a T-annotation line (text-bound).
    Returns (ann_id, ann_type, type_span_field, ann_text) or None.
    Format: T<id>TAB<type> <start> <end>TAB<text>

    type_span_field is the full second tab-delimited field ("Type start end",
    which may include ';' for discontinuous spans), preserved verbatim so that
    it can be copied wholesale to the output.
    """
    line = raw.rstrip("\n")
    if not line.startswith("T"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 3:
        return None
    ann_id = parts[0].strip()
    type_span_field = parts[1].strip()
    ann_type = type_span_field.split()[0]  # first token in the type+span field
    ann_text = parts[2].strip()
    return ann_id, ann_type, type_span_field, ann_text


def load_reference(path: Path) -> dict:
    """
    Build  type -> [(ann_id, type_span_field, ann_text), ...]  from
    PATH_ANNOTATIONS.  Only T-lines are considered.
    """
    ref: dict[str, list] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            parsed = parse_t_line(raw)
            if parsed is not None:
                ann_id, ann_type, type_span_field, ann_text = parsed
                ref.setdefault(ann_type, []).append((ann_id, type_span_field, ann_text))
    return ref


# ---------------------------------------------------------------------------
# Edit distance
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str, max_dist: int = None) -> int:
    """
    Compute the Levenshtein (edit) distance between strings *a* and *b*.

    If *max_dist* is given the function returns early with max_dist + 1 as
    soon as it is certain the true distance exceeds max_dist, avoiding
    unnecessary work for long strings that clearly do not match.
    """
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)

    # Make sure a is the shorter string (minor optimisation)
    if len_a > len_b:
        a, b = b, a
        len_a, len_b = len_b, len_a

    # If the length difference alone exceeds the threshold, bail out early
    if max_dist is not None and (len_b - len_a) > max_dist:
        return max_dist + 1

    # Standard DP with two rows
    prev = list(range(len_a + 1))
    for j in range(1, len_b + 1):
        curr = [j] + [0] * len_a
        for i in range(1, len_a + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(
                prev[i] + 1,  # deletion
                curr[i - 1] + 1,  # insertion
                prev[i - 1] + cost,  # substitution
            )
        # Early exit: if the minimum value in this row already exceeds the
        # threshold we know the final distance will be at least that large
        if max_dist is not None and min(curr) > max_dist:
            return max_dist + 1
        prev = curr

    return prev[len_a]


def find_best_match(ann_type: str, ann_text: str,
                    reference: dict, max_dist: int) -> tuple:
    """
    Search *reference* for the component with the same type and the smallest
    edit distance to *ann_text*, provided that distance <= max_dist.

    Returns (best_id, best_type_span, best_text, best_dist) or
    (None, None, None, None) if no candidate is within the threshold.

    If two candidates share the same minimum distance the match is ambiguous;
    (None, None, None, None) is returned so the caller can warn and skip.
    """
    candidates = reference.get(ann_type, [])
    if not candidates:
        return None, None, None, None

    best_dist = max_dist + 1  # sentinel: "no match yet"
    best_id = None
    best_type_span = None
    best_text = None
    ambiguous = False

    for ref_id, ref_type_span, ref_text in candidates:
        d = levenshtein(ann_text, ref_text, max_dist=max_dist)
        if d <= max_dist:
            if d < best_dist:
                best_dist = d
                best_id = ref_id
                best_type_span = ref_type_span
                best_text = ref_text
                ambiguous = False
            elif d == best_dist:
                ambiguous = True  # tie — caller will handle

    if ambiguous:
        return None, None, None, None  # signal tie to caller

    return best_id, best_type_span, best_text, best_dist


# ---------------------------------------------------------------------------
# ID remapping logic
# ---------------------------------------------------------------------------

def apply_id_map(lines: list[str], id_map: dict[str, str],
                 t_line_content_update: dict = None) -> list[str]:
    """
    Apply *id_map* (old_id -> new_id) to a list of raw brat annotation lines.

    - T-lines: the first tab-delimited field (the ID itself) is replaced.
               If *t_line_content_update* is provided and contains an entry
               for the NEW id, the T-line's second field (type+span) and
               third field (text) are also overwritten with those values.
    - R-lines: every occurrence of  :old_id  followed by whitespace or end-of-
               line is replaced (covers Arg1:T13, Arg2:T13, etc.).
    - All other lines are passed through unchanged.

    *t_line_content_update* maps  new_id -> (type_span_field, text).
    """
    if not id_map:
        return lines

    # Pre-compile one regex per old_id for R-line replacement
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
    """Return a temporary ID that cannot appear in normal brat files."""
    return f"TTEMP{index}"


def compute_remaps(filepath: Path, reference: dict, max_dist: int) -> dict:
    """
    Scan *filepath* and return all proposed remaps without touching the file.

    Returns a dict with:
        proposed     – list of
                       (old_id, new_id, dist,
                        orig_text, ref_text,
                        orig_type_span, ref_type_span)
        conflicts    – list of (old_id, new_id) that cannot be applied as-is
        ambiguous    – list of old_ids where two reference entries tied
        existing_ids – set of all T-ids currently in the file

    A remap is also proposed when old_id == new_id but the span or text
    differs — in that case the id is effectively unchanged while the span
    and text are corrected.
    """
    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

    full_remap: dict[str, str] = {}
    remap_meta: dict[str, tuple] = {}
    existing_ids: set[str] = set()
    ambiguous_ids: list[str] = []

    for raw in original_lines:
        parsed = parse_t_line(raw)
        if parsed is None:
            continue
        old_id, ann_type, orig_type_span, ann_text = parsed
        existing_ids.add(old_id)

        new_id, ref_type_span, ref_text, dist = find_best_match(
            ann_type, ann_text, reference, max_dist
        )

        if new_id is None and ref_text is None:
            candidates = reference.get(ann_type, [])
            tie_dist = max_dist + 1
            tie_count = 0
            for _, _, rt in candidates:
                d = levenshtein(ann_text, rt, max_dist=max_dist)
                if d <= max_dist:
                    if d < tie_dist:
                        tie_dist = d
                        tie_count = 1
                    elif d == tie_dist:
                        tie_count += 1
            if tie_count > 1:
                ambiguous_ids.append(old_id)
            continue

        # Propose an update if ANY of id / span / text differs
        if (old_id != new_id
                or orig_type_span != ref_type_span
                or ann_text != ref_text):
            full_remap[old_id] = new_id
            remap_meta[old_id] = (dist, ann_text, ref_text,
                                  orig_type_span, ref_type_span)

    # Detect conflicts (only meaningful when id actually changes)
    conflict_olds: set[str] = set()
    for old_id, new_id in full_remap.items():
        if old_id == new_id:
            continue  # in-place content update, no id collision possible
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
    Apply an approved subset of remaps to *filepath* and write it back.

    *approved* is a list of
        (old_id, new_id, dist, orig_text, ref_text,
         orig_type_span, ref_type_span).

    The T-line's id, type+span field and text are all replaced with the
    reference values.  R-lines that reference the old id are updated to
    use the new id.  A two-phase temp-id rename keeps chains and cycles
    safe even though content is rewritten in the same pass.

    Returns the number of components actually updated.
    """
    if not approved:
        return 0

    effective_remap: dict[str, str] = {}
    content_update: dict[str, tuple] = {}  # new_id -> (type_span, text)
    for entry in approved:
        old_id, new_id, _dist, _orig_text, ref_text, _orig_span, ref_span = entry
        effective_remap[old_id] = new_id
        content_update[new_id] = (ref_span, ref_text)

    original_lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)

    # Two-phase rename to handle chains & cycles safely.
    # Phase 1 moves ids to unique temp slots; phase 2 moves them to their
    # final ids AND rewrites the T-line's span/text in the same pass.
    temp_map: dict[str, str] = {}
    final_map: dict[str, str] = {}
    for idx, (old_id, new_id) in enumerate(effective_remap.items()):
        tmp = build_temp_id(idx)
        temp_map[old_id] = tmp
        final_map[tmp] = new_id

    lines = apply_id_map(original_lines, temp_map)
    lines = apply_id_map(lines, final_map, t_line_content_update=content_update)
    filepath.write_text("".join(lines), encoding="utf-8")
    return len(effective_remap)


# ---------------------------------------------------------------------------
# Interactive confirmation (dry-run)
# ---------------------------------------------------------------------------

def ask_user(old_id: str, new_id: str, dist: int,
             orig_text: str, ref_text: str,
             orig_span: str, ref_span: str) -> str:
    """
    Print a single proposed remap and prompt the user for a decision.

    Returns one of:
        'y' – approve this remap
        'n' – reject this remap
        'a' – approve all remaining remaps without further prompting
        'q' – reject all remaining remaps and stop asking
    """
    if old_id == new_id:
        print(f"\n  {old_id}  (id unchanged — span/text update, dist={dist})")
    else:
        print(f"\n  {old_id}  ->  {new_id}  (dist={dist})")
    if orig_span != ref_span:
        print(f"    original span : {orig_span}")
        print(f"    reference span: {ref_span}")
    if dist > 0:
        print(f"    original text : {orig_text}")
        print(f"    reference text: {ref_text}")
    while True:
        try:
            answer = input("  Apply this remap? [y]es / [n]o / [a]ll / [q]uit all: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 'q'
        if answer in ('y', 'n', 'a', 'q'):
            return answer
        print("  Please enter y, n, a, or q.")


def interactive_filter(proposed: list, filename: str) -> tuple[list, list]:
    """
    Walk through *proposed* remaps interactively, asking the user to approve
    or reject each one.

    Returns (approved, rejected) lists of remap tuples.
    """
    approved = []
    rejected = []
    auto_approve = False

    print(f"\n--- {filename}: {len(proposed)} proposed remap(s) ---")

    for entry in proposed:
        old_id, new_id, dist, orig_text, ref_text, orig_span, ref_span = entry
        if auto_approve:
            approved.append(entry)
            if old_id == new_id:
                print(f"  {old_id}  (span/text update, dist={dist})  [auto-approved]")
            else:
                print(f"  {old_id}  ->  {new_id}  (dist={dist})  [auto-approved]")
            continue

        answer = ask_user(old_id, new_id, dist,
                          orig_text, ref_text, orig_span, ref_span)
        if answer == 'y':
            approved.append(entry)
        elif answer == 'n':
            rejected.append(entry)
        elif answer == 'a':
            approved.append(entry)
            auto_approve = True
            print("  (approving all remaining remaps for this file)")
        elif answer == 'q':
            rejected.append(entry)
            # Reject everything that remains
            remaining = proposed[proposed.index(entry) + 1:]
            rejected.extend(remaining)
            print("  (rejecting all remaining remaps for this file)")
            break

    return approved, rejected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Remap component IDs in brat files to match a reference annotation file "
                    "using fuzzy text matching (same type + edit distance within threshold).\n\n"
                    "With --dry-run, each proposed remap is shown interactively and you are "
                    "asked whether to include it. Files are never modified in dry-run mode."
    )
    parser.add_argument("--folder", "-f", required=True,
                        help="Folder with original brat .ann files (FOLDER_ORIGINAL).")
    parser.add_argument("--ann", "-a", required=True,
                        help="Reference annotation file (PATH_ANNOTATIONS).")
    parser.add_argument("--max-distance", "-d", type=int, default=5,
                        help="Maximum edit distance to consider two texts similar (default: 2).")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Interactively review each proposed remap one by one. "
                             "Approved remaps (y/a) are applied immediately; "
                             "rejected ones (n/q) are skipped.")
    args = parser.parse_args()

    if args.max_distance < 0:
        sys.exit("ERROR: --max-distance must be >= 0.")

    folder = Path(args.folder)
    ann_path = Path(args.ann)

    if not folder.is_dir():
        sys.exit(f"ERROR: folder not found: {folder}")
    if not ann_path.is_file():
        sys.exit(f"ERROR: annotation file not found: {ann_path}")

    reference = load_reference(ann_path)
    total_ref = sum(len(v) for v in reference.values())
    print(f"Reference loaded: {total_ref} component(s) from {ann_path.name}")
    print(f"Similarity threshold: edit distance <= {args.max_distance}")

    ann_files = sorted(folder.glob("*.ann"))
    if not ann_files:
        sys.exit(f"No .ann files found in {folder}")

    print(f"Processing {len(ann_files)} file(s) …")
    if args.dry_run:
        print("(INTERACTIVE mode — approved remaps ARE written to disk)")
        print("For each proposed remap: [y]es apply / [n]o skip / [a]ll apply rest / [q]uit skip rest\n")

    total_remapped = 0
    total_rejected = 0
    total_conflicts = 0
    total_ambiguous = 0

    for fp in ann_files:
        result = compute_remaps(fp, reference, max_dist=args.max_distance)

        nothing = (not result["proposed"] and
                   not result["conflicts"] and
                   not result["ambiguous"])
        if nothing:
            print(f"\n  {fp.name}: no similar components found")
            continue

        if args.dry_run:
            # ---- Interactive review + selective apply -----------------------
            if result["proposed"]:
                approved, rejected = interactive_filter(result["proposed"], fp.name)
            else:
                approved, rejected = [], []

            if approved:
                n = apply_remaps(fp, approved)
                print(f"  {fp.name}: applied {n} remap(s)")
            if rejected:
                print(f"  {fp.name}: skipped {len(rejected)} remap(s)")
            total_remapped += len(approved)
            total_rejected += len(rejected)

        else:
            # ---- Non-interactive: apply all proposed remaps -----------------
            n = apply_remaps(fp, result["proposed"])
            print(f"  {fp.name}: remapped {n} id(s)")
            total_remapped += n

        # Always report conflicts and ambiguous
        if result["conflicts"]:
            print(f"  {fp.name}: SKIPPED {len(result['conflicts'])} conflict(s) "
                  f"(target id occupied by a different non-remapped component)")
            for old_id, new_id in result["conflicts"]:
                print(f"    {old_id}  ->  {new_id}  [CONFLICT — {new_id} already exists]")
            total_conflicts += len(result["conflicts"])

        if result["ambiguous"]:
            print(f"  {fp.name}: SKIPPED {len(result['ambiguous'])} ambiguous match(es) "
                  f"(two or more reference components equally close)")
            for old_id in result["ambiguous"]:
                print(f"    {old_id}  [AMBIGUOUS]")
            total_ambiguous += len(result["ambiguous"])

    print(f"\nDone.")
    if args.dry_run:
        print(f"  Total ids applied (approved)     : {total_remapped}")
        print(f"  Total ids skipped (rejected)     : {total_rejected}")
    else:
        print(f"  Total ids remapped               : {total_remapped}")
    print(f"  Total conflicts skipped          : {total_conflicts}")
    print(f"  Total ambiguous matches skipped  : {total_ambiguous}")
    if total_conflicts:
        print("  NOTE: conflicting remaps were skipped — resolve manually if needed.")
    if total_ambiguous:
        print("  NOTE: ambiguous remaps were skipped — lower --max-distance or resolve manually.")
    if not args.dry_run and total_remapped == 0 and total_conflicts == 0:
        print("\n  Tip: use --dry-run to review and selectively apply remaps.")


if __name__ == "__main__":
    main()
