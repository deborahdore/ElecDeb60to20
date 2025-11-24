import os
import random

import rootutils
import spacy
from brat_parser import get_entities_relations_attributes_groups

nlp = spacy.load("en_core_web_sm")
rootutils.setup_root(__file__, indicator=".project-root", pythonpath=True, cwd=True)


def brat_to_conll(txt_path: str, ann_path: str, out_path: str, punctuation: bool = True):
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    print(f"Parsing: {txt_path}")

    entities, _, _, _ = get_entities_relations_attributes_groups(ann_path)
    char2label = ["O"] * len(text)

    for entity in entities.values():
        label = entity.type
        spans = entity.span

        first = True
        for (s, e) in spans:
            for i in range(s, e):
                if first:
                    char2label[i] = "B-" + label
                    first = False
                else:
                    char2label[i] = "I-" + label

    doc = nlp(text)
    prev_bio = "O"

    with open(out_path, "w", encoding="utf-8") as out:
        for token in doc:
            tok_text = token.text
            start = token.idx
            end = start + len(tok_text)

            if tok_text == "\n":
                out.write("\n")
                prev_bio = "O"
                continue

            labels = [char2label[i] for i in range(start, end) if i < len(char2label)]

            # If no label at all → O
            if not labels or all(l == "O" for l in labels):
                bio = "O"
            else:
                # Determine entity type (Premise, Claim...)
                types = {l[2:] for l in labels if l != "O"}
                ent_type = types.pop()

                if start < len(char2label) and char2label[start].startswith("B-"):
                    bio = f"B-{ent_type}"
                else:
                    bio = f"I-{ent_type}"

            if punctuation and (token.text in {".", ";", "!", "?"}) and prev_bio != "O" and bio == "O":
                bio = f"I-{prev_bio.split('-')[-1]}"

            out.write(f"{tok_text}\t_\t_\t{bio}\n")
            prev_bio = bio

        out.write("\n")

    print(f"CoNLL written to {out_path}")


def split(conll_path: str, out_path: str, train_ratio: float = 0.7, test_ratio: float = 0.2, seed: int = 42):
    files = sorted(f for f in os.listdir(conll_path) if f.endswith(".conll"))
    total = len(files)
    print(f"Total debates: {total}")

    random.seed(seed)

    train_size = int(total * train_ratio)
    test_size = int(total * test_ratio)

    train = random.sample(files, train_size)
    remaining = [f for f in files if f not in train]

    test = random.sample(remaining, test_size)
    train_set, test_set = set(train), set(test)

    dev = [f for f in files if f not in train_set and f not in test_set]

    assert len(train) + len(test) + len(dev) == total
    assert train_set.isdisjoint(test_set)
    assert train_set.isdisjoint(dev)
    assert test_set.isdisjoint(dev)

    def write_split(output_name: str, split_files):
        output_path = os.path.join(out_path, output_name)
        with open(output_path, "w", encoding="utf-8") as out_f:
            for fname in split_files:
                file_path = os.path.join(conll_path, fname)
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read().rstrip()
                out_f.write(text + "\n")  # ensure separation
        print(f"Wrote {output_name} ({len(split_files)} files)")

    write_split("train.conll", train)
    write_split("test.conll", test)
    write_split("dev.conll", dev)

    return train, test, dev


if __name__ == '__main__':
    os.makedirs("./data/components/conll", exist_ok=True)

    files = sorted([
        f
        for f in os.listdir("./data/annotations/components")
        if f.endswith(".ann")
    ])
    for file in files:
        file_name = file.split(".")[0]
        brat_to_conll(
            txt_path=os.path.join("./data/annotations/components/") + file_name + ".txt",
            ann_path=os.path.join("./data/annotations/components/") + file_name + ".ann",
            out_path=os.path.join("./data/components/conll/") + file_name + ".conll"
        )

    split(conll_path="./data/components/conll", out_path="./data/components")
