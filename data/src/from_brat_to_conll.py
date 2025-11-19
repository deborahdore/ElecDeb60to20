import os

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

    with open(out_path, "w", encoding="utf-8") as out:
        for token in doc:
            tok_text = token.text
            start = token.idx
            end = start + len(tok_text)

            if tok_text == "\n":
                out.write("\n")
                continue

            # BIO by majority voting on character labels
            span_labels = char2label[start:end]
            if all(l == "O" for l in span_labels):
                bio = "O"
            else:
                # If there is a B- tag inside token → use that
                b_tags = [l for l in span_labels if l.startswith("B-")]
                if b_tags:
                    bio = b_tags[0]
                else:
                    # otherwise use most common I-tag
                    i_tags = [l for l in span_labels if l.startswith("I-")]
                    bio = i_tags[0] if i_tags else "O"

            out.write(f"{tok_text}\t_\t_\t{bio}\n")

        # Sentence separator
        out.write("\n")

    print(f"CoNLL written to {out_path}")


if __name__ == '__main__':
    os.makedirs("./data/components", exist_ok=True)

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
            out_path=os.path.join("./data/components/") + file_name + ".conll"
        )
