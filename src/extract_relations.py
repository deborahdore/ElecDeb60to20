"""
brat_to_relations.py

Converts BRAT .ann annotation files into CSV relation tables.

Each output CSV has one row per annotated relation, with columns for the
subject and object component texts, types, spans, and the relation type.

Output directory: data/relations/
"""

import logging
import os
import re

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ANN_DIR = os.path.join(BASE, "data", "annotations", "relations")
OUT_DIR = os.path.join(BASE, "data", "relations", "csv")


def parse_ann_file(ann_path: str) -> list[dict]:
    """Parse a single BRAT .ann file and return a list of relation dicts.

    Each dict contains:
        subj        – text of the subject (source) component
        subj_type   – annotation type of the subject
        subj_span   – character span tuple of the subject
        obj         – text of the object (target) component
        obj_type    – annotation type of the object
        obj_span    – character span tuple of the object
        relation    – relation type label
    """
    entities: dict[str, dict] = {}
    raw_relations: list[tuple[str, str, str]] = []  # (rel_type, subj_id, obj_id)

    with open(ann_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("*") or line.startswith("#"):
                continue

            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue

            ann_id, rest = parts[0], parts[1]

            # Entity line: T1   Claim 1375 1537   text...
            if ann_id.startswith("T"):
                m = re.match(r"(\S+)\s+(\d+)\s+(\d+)", rest)
                if m:
                    etype = m.group(1)
                    start, end = int(m.group(2)), int(m.group(3))
                    text = parts[2] if len(parts) == 3 else ""
                    entities[ann_id] = {"type": etype, "span": (start, end), "text": text}

            # Relation line: R1   Support Arg1:T1 Arg2:T43
            elif ann_id.startswith("R"):
                tokens = rest.split()
                if len(tokens) >= 3:
                    rel_type = tokens[0]
                    arg1 = arg2 = None
                    for tok in tokens[1:]:
                        if tok.startswith("Arg1:"):
                            arg1 = tok[5:]
                        elif tok.startswith("Arg2:"):
                            arg2 = tok[5:]
                    if arg1 and arg2:
                        raw_relations.append((rel_type, arg1, arg2))

    # Build a quick-lookup dict keyed by entity id
    components: dict[str, dict] = entities

    rows = []
    for rel_type, subj_id, obj_id in raw_relations:

        # Skip any relation whose endpoints are not present in the entity index
        if subj_id not in components:
            logger.warning("  Unknown subject entity '%s' – skipping relation", subj_id)
            continue
        if obj_id not in components:
            logger.warning("  Unknown object entity '%s' – skipping relation", obj_id)
            continue

        rows.append({
            "subj": components[subj_id]["text"],
            "subj_type": components[subj_id]["type"],
            "subj_span": components[subj_id]["span"],
            "obj": components[obj_id]["text"],
            "obj_type": components[obj_id]["type"],
            "obj_span": components[obj_id]["span"],
            "relation": rel_type,
        })

    return rows


def process_all(ann_dir: str, out_dir: str) -> None:
    """Process every .ann file in *ann_dir* and write CSVs to *out_dir*."""
    os.makedirs(out_dir, exist_ok=True)

    ann_files = [f for f in os.listdir(ann_dir) if f.endswith(".ann")]

    if not ann_files:
        logger.warning("No .ann files found in %s", ann_dir)
        return

    logger.info("Found %d .ann file(s) in %s", len(ann_files), ann_dir)

    out_path = os.path.join(out_dir, f"{os.path.basename(ann_dir)}.csv")
    ok = skipped = 0
    rows = []
    for filename in sorted(ann_files):
        ann_path = os.path.join(ann_dir, filename)

        try:
            file_rows = parse_ann_file(ann_path)
            rows.extend(file_rows)
            logger.info("  ✓  %s  →  %s  (%d relation(s))", filename, out_path, len(file_rows))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("  ✗  %s  –  %s", filename, exc)
            skipped += 1
    pd.DataFrame(rows).to_csv(out_path, index=False)

    logger.info("Done. %d succeeded, %d failed.", ok, skipped)


if __name__ == "__main__":
    process_all(ANN_DIR, OUT_DIR)
