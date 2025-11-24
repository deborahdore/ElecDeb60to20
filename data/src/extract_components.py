import os
import random

import rootutils
import spacy
from brat_parser import get_entities_relations_attributes_groups

nlp = spacy.load("en_core_web_sm")
rootutils.setup_root(__file__, indicator=".project-root", pythonpath=True, cwd=True)


def brat_to_conll(txt_path: str, ann_path: str, out_path: str):
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    print(f"Parsing: {txt_path}")
    # Parse annotations
    entities, _, _, _ = get_entities_relations_attributes_groups(ann_path)

    # Flatten spans for lookup
    char2label = ["O"] * len(text)

    for entity in entities.values():
        spans = entity.span
        label = entity.type
        for (s, e) in spans:
            # Assign B/I tags
            first = True
            for i in range(s, e):
                if first:
                    char2label[i] = "B-" + label
                    first = False
                else:
                    char2label[i] = "I-" + label

    doc = nlp(text)

    prev_tok = None
    prev_bio = None

    with open(out_path, "w", encoding="utf-8") as out:
        for token in doc:
            tok_text = token.text
            start = token.idx
            end = start + len(tok_text)

            # BIO by majority voting on character labels
            span_labels = char2label[start:end]
            if all(l == "O" for l in span_labels):
                bio = "O"
            else:
                b_tags = [l for l in span_labels if l.startswith("B-")]
                if b_tags:
                    bio = b_tags[0]
                else:
                    i_tags = [l for l in span_labels if l.startswith("I-")]
                    bio = i_tags[0] if i_tags else "O"

            # if current token is I-X but previous was O → previous becomes B-X
            if bio.startswith("I-"):
                label = bio[2:]
                if prev_bio is not None and prev_bio == "O":
                    prev_bio = "B-" + label

            if prev_tok is not None:
                if prev_tok != "\n":
                    out.write(f"{prev_tok}\t_\t_\t{prev_bio}\n")
                else:
                    out.write("\n")

            prev_tok = tok_text
            prev_bio = bio

        if prev_tok is not None:
            if prev_tok != "\n":
                out.write(f"{prev_tok}\t_\t_\t{prev_bio}\n")
            else:
                out.write("\n")

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
