#!/usr/bin/env python3
"""
Clean a brat .ann file in place:

  Step 1 - delete exact duplicate relations
           (same relation type + same Arg1 + same Arg2).
  Step 2 - deduplicate text components (T lines) whose TYPE is identical and
           whose text has Levenshtein distance < 3. Keep the first occurrence
           and remap every relation referencing the removed IDs to the kept ID.

After step 2, a final pass removes any relation duplicates that the remapping
may have produced.

Usage:
    python clean_ann.py --file <path/to/file.ann>

The input file is rewritten in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Levenshtein distance with early exit
# ---------------------------------------------------------------------------
def levenshtein(a: str, b: str, cap: int) -> int:
    """Return Levenshtein(a, b), or cap+1 if the distance exceeds cap."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        row_min = curr[0]
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + (ca != cb),  # substitution
            )
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > cap:
            return cap + 1
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_component(line: str):
    """Parse a T line:  'T1<TAB>Type start end[;start end ...]<TAB>text'.

    Returns (tid, ctype, spans, meta, text) where `spans` is the offset
    portion of the meta (everything after the type token), used to require
    identical spans when matching duplicates.
    """
    parts = line.rstrip("\n").split("\t")
    tid = parts[0]
    meta = parts[1]  # e.g. "Premise 1153 1221"
    text = parts[2] if len(parts) > 2 else ""
    head, _, spans = meta.partition(" ")  # "Premise", " ", "1153 1221"
    ctype = head  # "Premise" / "Claim" / ...
    return tid, ctype, spans, meta, text


def parse_relation(line: str):
    """Parse an R line:  'R1<TAB>Type Arg1:Ta Arg2:Tb'."""
    parts = line.rstrip("\n").split("\t")
    rid = parts[0]
    fields = parts[1].split()
    rtype = fields[0]
    arg1 = fields[1].split(":", 1)[1]
    arg2 = fields[2].split(":", 1)[1]
    return rid, rtype, arg1, arg2


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def clean(path: Path, edit_cap: int = 2) -> None:
    in_path = path
    out_path = path
    components: list[tuple] = []  # (tid, ctype, spans, meta, text, raw_line)
    relations: list[tuple] = []  # (rid, rtype, arg1, arg2, raw_line)
    other: list[str] = []

    with in_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            if line.startswith("T"):
                tid, ctype, spans, meta, text = parse_component(line)
                components.append((tid, ctype, spans, meta, text, line.rstrip("\n")))
            elif line.startswith("R"):
                rid, rtype, arg1, arg2 = parse_relation(line)
                relations.append((rid, rtype, arg1, arg2, line.rstrip("\n")))
            else:
                other.append(line.rstrip("\n"))

    print(f"Input : {len(components)} components, {len(relations)} relations")

    # -------------------------------------------------------------------
    # Step 1 - drop exact-duplicate relations (same type + Arg1 + Arg2)
    # -------------------------------------------------------------------
    seen_rel: dict[tuple, str] = {}
    kept_rel: list[tuple] = []
    dup_rel: list[tuple] = []
    for rid, rtype, arg1, arg2, raw in relations:
        key = (rtype, arg1, arg2)
        if key in seen_rel:
            dup_rel.append((rid, seen_rel[key], key))
        else:
            seen_rel[key] = rid
            kept_rel.append((rid, rtype, arg1, arg2, raw))

    print(f"\nStep 1 - exact duplicate relations removed: {len(dup_rel)}")
    for rid, kept_rid, key in dup_rel:
        print(f"  removed {rid}  (duplicate of {kept_rid})  {key[0]} {key[1]} {key[2]}")

    # -------------------------------------------------------------------
    # Step 2 - dedupe components: same TYPE + same SPANS + edit distance < 3
    #          keep the first occurrence; build tid -> kept_tid map
    # -------------------------------------------------------------------
    mapping: dict[str, str] = {}
    kept_comps: list[tuple] = []
    removed_comps: list[tuple] = []

    for tid, ctype, spans, meta, text, raw in components:
        match_tid = None
        for ktid, kctype, kspans, _kmeta, ktext, _kraw in kept_comps:
            if (kctype == ctype
                    and kspans == spans
                    and levenshtein(text, ktext, edit_cap) <= edit_cap):
                match_tid = ktid
                break
        if match_tid is None:
            kept_comps.append((tid, ctype, spans, meta, text, raw))
            mapping[tid] = tid
        else:
            mapping[tid] = match_tid
            removed_comps.append((tid, match_tid, ctype, text))

    print(f"\nStep 2 - duplicate components removed "
          f"(same type, same spans, edit distance < 3): {len(removed_comps)}")
    for tid, kept, ctype, text in removed_comps:
        snippet = text if len(text) < 70 else text[:67] + "..."
        print(f"  removed {tid} -> kept {kept}  [{ctype}]  \"{snippet}\"")

    # -------------------------------------------------------------------
    # Apply mapping to the surviving relations + final dedupe pass.
    # -------------------------------------------------------------------
    final_rel: list[tuple] = []
    seen_rel2: dict[tuple, str] = {}
    secondary_dups: list[tuple] = []
    for rid, rtype, arg1, arg2, _raw in kept_rel:
        new_a1 = mapping.get(arg1, arg1)
        new_a2 = mapping.get(arg2, arg2)
        key = (rtype, new_a1, new_a2)
        if key in seen_rel2:
            secondary_dups.append((rid, seen_rel2[key], key))
            continue
        seen_rel2[key] = rid
        new_raw = f"{rid}\t{rtype} Arg1:{new_a1} Arg2:{new_a2}"
        final_rel.append((rid, new_raw))

    if secondary_dups:
        print(f"\nPost-remap - duplicate relations created by remapping "
              f"and removed: {len(secondary_dups)}")
        for rid, kept_rid, key in secondary_dups:
            print(f"  removed {rid}  (now duplicate of {kept_rid})  "
                  f"{key[0]} {key[1]} {key[2]}")

    # -------------------------------------------------------------------
    # Write the cleaned file (original IDs preserved, original order kept).
    # -------------------------------------------------------------------
    out_lines: list[str] = []
    out_lines.extend(raw for _tid, _ct, _sp, _m, _t, raw in kept_comps)
    out_lines.extend(raw for _rid, raw in final_rel)
    out_lines.extend(other)

    with out_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"\nOutput: {len(kept_comps)} components, {len(final_rel)} relations")
    print(f"Rewritten in place: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean a brat .ann file in place: remove exact-duplicate "
                    "relations and merge near-duplicate components "
                    "(same type, edit distance < 3).",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the .ann file to clean (rewritten in place).",
    )
    args = parser.parse_args()

    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        sys.exit(f"Input file not found: {path}")

    clean(path)


if __name__ == "__main__":
    main()
