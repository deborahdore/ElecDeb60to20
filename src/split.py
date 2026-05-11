import os

import pandas as pd
from sklearn.model_selection import train_test_split

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELATION_DIR = os.path.join(BASE, "data", "relations")
COMPONENT_DIR = os.path.join(BASE, "data", "components")
FALLACY_DIR = os.path.join(BASE, "data", "fallacies")

COMPONENT_CONLL_DIR = os.path.join(COMPONENT_DIR, "conll")
RELATION_CSV_DIR = os.path.join(RELATION_DIR, "csv")
FALLACY_CONLL_DIR = os.path.join(FALLACY_DIR, "conll")
FALLACY_CSV_DIR = os.path.join(FALLACY_DIR, "csv")


def load_conll(path):
    """Read a CoNLL file and return its contents as a string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_conll(path, content):
    """Write a string to a CoNLL file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == '__main__':
    # Build file list from the components conll directory (base split source).
    # Exclude any previously generated split files (train/dev/test) so re-runs stay clean.
    SPLIT_NAMES = {"train", "dev", "test"}
    files = [
        os.path.splitext(f)[0]
        for f in os.listdir(COMPONENT_CONLL_DIR)
        if f.endswith(".conll") and os.path.splitext(f)[0] not in SPLIT_NAMES
    ]
    train, test = train_test_split(files, test_size=0.2, random_state=42)
    test, dev = train_test_split(test, test_size=0.5, random_state=42)

    splits = {"train": train, "dev": dev, "test": test}

    for split_name, split_files in splits.items():

        # ── Components (CoNLL) ──────────────────────────────────────────────
        component_parts = []
        for f in split_files:
            path = os.path.join(COMPONENT_CONLL_DIR, f + ".conll")
            if os.path.exists(path):
                component_parts.append(load_conll(path))
        save_conll(
            os.path.join(COMPONENT_DIR, split_name + ".conll"),
            "\n".join(component_parts),
        )

        # ── Relations (CSV) ─────────────────────────────────────────────────
        relation_dfs = []
        for f in split_files:
            path = os.path.join(RELATION_CSV_DIR, f + ".csv")
            if os.path.exists(path):
                try:
                    relation_dfs.append(pd.read_csv(path))
                except pd.errors.EmptyDataError:
                    pass
        if relation_dfs:
            pd.concat(relation_dfs, ignore_index=True).to_csv(
                os.path.join(RELATION_DIR, split_name + ".csv"), index=False
            )

        # ── Fallacies (CoNLL) ───────────────────────────────────────────────
        fallacy_parts = []
        for f in split_files:
            path = os.path.join(FALLACY_CONLL_DIR, f + ".conll")
            if os.path.exists(path):
                fallacy_parts.append(load_conll(path))
        save_conll(
            os.path.join(FALLACY_DIR, split_name + ".conll"),
            "\n".join(fallacy_parts),
        )

        # ── Fallacies (CSV) ─────────────────────────────────────────────────
        fallacy_dfs = []
        for f in split_files:
            path = os.path.join(FALLACY_CSV_DIR, f + ".csv")
            if os.path.exists(path):
                try:
                    fallacy_dfs.append(pd.read_csv(path))
                except pd.errors.EmptyDataError:
                    pass
        if fallacy_dfs:
            pd.concat(fallacy_dfs, ignore_index=True).to_csv(
                os.path.join(FALLACY_DIR, split_name + ".csv"), index=False
            )

        print(
            f"[{split_name}] {len(component_parts)} components | "
            f"{len(relation_dfs)} relations | "
            f"{len(fallacy_parts)} fallacies (conll) | "
            f"{len(fallacy_dfs)} fallacies (csv)"
        )
