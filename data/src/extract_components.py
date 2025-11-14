import os
import re

import nltk
import numpy as np
import pandas as pd
import rootutils
from brat_parser import get_entities_relations_attributes_groups
from tqdm import tqdm

rootutils.setup_root(__file__, indicator=".project-root", pythonpath=True, cwd=True)

data_path = 'data/'
annotations_base_path = 'data/ann/'
full_debates_file = "data/full_debates.csv"

os.makedirs(os.path.join(data_path, "components"), exist_ok=True)


def parse_annotations():
    df = pd.read_csv(full_debates_file).sample(n=20)

    annotated_df = []
    previous_folder = ""
    all_entities = []
    # all_relations = []
    # all_attributes = []
    # all_groups = []
    for idx, row in tqdm(df.iterrows(), total=len(df)):
        date = row.date
        speaker = row.speaker
        speech = row.concatenated_speech

        # load all annotations for that date
        day, month, year = date.split("/")
        folder = os.path.join(annotations_base_path, year, f"{day}_{month.zfill(2)}")

        try:
            files = [
                os.path.join(folder, file)
                for file in os.listdir(folder)
                if file.endswith(".ann")
            ]
        except:
            continue

        # reload annotation files only when folder changes
        if folder != previous_folder:
            previous_folder = folder
            all_entities = []
            # all_relations = []
            # all_attributes = []
            # all_groups = []

            for fname in files:
                print("Parsing:", fname)
                entities, relations, attributes, groups = get_entities_relations_attributes_groups(fname)

                all_entities.extend(entities.values())
                # all_relations.extend(relations.values())
                # all_attributes.extend(attributes.values())
                # all_groups.extend(groups.values())

        # annotate the current speech
        annotated_sentences = []

        for sentence in nltk.sent_tokenize(speech):
            updated_sentence = sentence
            for entity in all_entities[:]:  # iterate over a shallow copy
                text = entity.text
                ent_type = entity.type

                # skip impossible matches
                if len(text.split()) > len(sentence.split()):
                    continue

                pattern = r"\b" + re.escape(text) + r"\b"
                if re.search(pattern, updated_sentence):
                    updated_sentence = re.sub(
                        pattern,
                        f"<{ent_type}>{text}</{ent_type}>",
                        updated_sentence
                    )
                    all_entities.remove(entity)  # safe now
                    break

            annotated_sentences.append(updated_sentence)

        annotated_df.append({
            "date": date,
            "speaker": speaker,
            "speech": " ".join(annotated_sentences)
        })
    annotated_df = pd.DataFrame(annotated_df)
    annotated_df.to_csv(os.path.join(data_path, "annotated_full_debates.csv"), index=False)
    return annotated_df


def transform_to_conll(annotated_df, output_file):
    # transform df to conll
    conll_lines = []
    for idx, entry in annotated_df.iterrows():
        speech = entry.speech
        # speaker = entry['speaker']

        # Split into sentences
        sentences = nltk.sent_tokenize(speech)

        for sentence in sentences:
            # Extract entities and their types from XML-like tags
            tokens = []
            current_entity = None

            # Parse the sentence with XML tags
            parts = re.split(r'(<[^>]+>|</[^>]+>)', sentence)

            for part in parts:
                if not part.strip():
                    continue

                # Opening tag
                if re.match(r'<([^/>]+)>$', part):
                    entity_type = re.match(r'<([^/>]+)>$', part).group(1)
                    current_entity = entity_type
                # Closing tag
                elif re.match(r'</([^>]+)>$', part):
                    current_entity = None
                # Text content
                else:
                    # Tokenize the text
                    words = part.split()
                    for i, word in enumerate(words):
                        if current_entity:
                            # Use BIO tagging scheme
                            if i == 0:
                                tag = f"B-{current_entity}"
                            else:
                                tag = f"I-{current_entity}"
                        else:
                            tag = "O"

                        conll_lines.append(f"{word}\t_\t_\t{tag}")

        # Blank line between rows
        conll_lines.append("")
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(conll_lines))
    print(f"CoNLL format saved to: {output_file}")


if __name__ == "__main__":
    annotated_df = parse_annotations()
    dates = np.unique(annotated_df['date'].values).tolist()
    print(dates)
    for date in dates:
        day, month, year = date.split("/")
        output_file = os.path.join(data_path, "components", f"{day}-{month}-{year}.conll")
        transform_to_conll(annotated_df[annotated_df['date'] == date], output_file)
