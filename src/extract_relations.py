import hashlib
import os
import random

import pandas as pd
import rootutils
from brat_parser import get_entities_relations_attributes_groups

rootutils.setup_root(__file__, indicator=".project-root", pythonpath=True, cwd=True)

PATH = "data/annotations/relations"
COMPONENTS_PATH = "data/components/csv"
RELATIONS_PATH = "data/relations/csv"


def save_to_csv(path, dataset):
    df = pd.DataFrame(dataset)
    print(f"Size df before dropping duplicates: {len(df)}")
    df = df.dropna().drop_duplicates().reset_index(drop=True)
    print(f"Size df after dropping duplicates: {len(df)}")
    df.to_csv(path, index=False)


def get_hash(text):
    return hashlib.md5(text.encode()).hexdigest()


def extract_relations():
    os.makedirs(COMPONENTS_PATH, exist_ok=True)
    os.makedirs(RELATIONS_PATH, exist_ok=True)

    component_dataset = []
    relation_dataset = []

    years = sorted(os.listdir(PATH))
    for year in years:
        year_components = []
        year_relations = []

        year_path = os.path.join(PATH, year)
        files = os.listdir(year_path)
        for file in files:
            entities, relations, _, _ = get_entities_relations_attributes_groups(os.path.join(year_path, file))

            id_to_unique_id = {}
            unique_id_to_text = {}

            for entity in sorted(entities.values(), key=lambda e: int(e.id[1:])):
                unique_id = year + "_" + \
                            get_hash(entity.id + entity.text + entity.type + str(entity.span[0][0]) + str(
                                entity.span[0][-1]))
                id_to_unique_id[entity.id] = unique_id
                unique_id_to_text[unique_id] = entity.text

                year_components.append({
                    "unique_id": unique_id,
                    "id": entity.id,
                    "year": year,
                    "text": entity.text,
                    "label": entity.type
                })

            for relation in relations.values():
                year_relations.append({
                    "source_unique_id": id_to_unique_id[relation.subj],
                    "target_unique_id": id_to_unique_id[relation.obj],
                    "source_id": relation.subj,
                    "target_id": relation.obj,
                    "source_text": unique_id_to_text[id_to_unique_id[relation.subj]],
                    "target_text": unique_id_to_text[id_to_unique_id[relation.obj]],
                    "relation_class": relation.type,
                    "year": year
                })

        save_to_csv(os.path.join(COMPONENTS_PATH, year + ".csv"), year_components)
        save_to_csv(os.path.join(RELATIONS_PATH, year + ".csv"), year_relations)

        component_dataset.extend(year_components)
        relation_dataset.extend(year_relations)

    save_to_csv(os.path.join(COMPONENTS_PATH, "components.csv"), component_dataset)
    save_to_csv(os.path.join(RELATIONS_PATH, "filtered_relations.csv"), relation_dataset)

def create_dataset():
    filtered_relations_path = os.path.join(RELATIONS_PATH, "../filtered_relations.csv")
    df = pd.read_csv(filtered_relations_path)

    # Remove Equivalent relations — keep only Support and Attack for binary classification
    df = df[df['relation_class'] != "Equivalent"].reset_index(drop=True)

    # Build subject and object pools: (year, source_unique_id, source_id, source_text)
    df_subject = df[['year', 'source_unique_id', 'source_id', 'source_text']].values.tolist()
    df_object = df[['year', 'target_unique_id', 'target_id', 'target_text']].values.tolist()

    # Set of existing (source_unique_id, target_unique_id) pairs for fast deduplication
    existing_pairs = set(zip(df['source_unique_id'], df['target_unique_id']))

    new_relations = []

    while len(new_relations) < len(df):
        arg_subject = random.choice(df_subject)

        # Filter objects to match the same year (same debate context)
        same_year_objects = [obj for obj in df_object if obj[0] == arg_subject[0]]
        if not same_year_objects:
            continue

        arg_object = random.choice(same_year_objects)

        # Skip if this pair already exists as a real relation
        if (arg_subject[1], arg_object[1]) in existing_pairs:
            continue

        new_relations.append({
            "source_unique_id": arg_subject[1],
            "target_unique_id": arg_object[1],
            "source_id": arg_subject[2],
            "target_id": arg_object[2],
            "source_text": arg_subject[3],
            "target_text": arg_object[3],
            "relation_class": "no_relation",
            "year": arg_subject[0]
        })

    df = pd.concat([df, pd.DataFrame(new_relations)], axis=0, ignore_index=True).dropna().reset_index(drop=True)
    print("Dataframe with fake relations: ", len(df))
    df.to_csv(os.path.join(RELATIONS_PATH, "relations.csv"), index=False)

def split_dataset():
    relations_path = os.path.join(RELATIONS_PATH, "relations.csv")
    df = pd.read_csv(relations_path)

    years = list(set(df["year"].tolist()))
    total = len(years)
    random.seed(123)

    train_size = int(total * 0.7)
    test_size = int(total * 0.2)

    train_years = random.sample(years, train_size)
    remaining = [y for y in years if y not in train_years]

    test_years = random.sample(remaining, test_size)
    dev_years = [y for y in remaining if y not in test_years]

    train = df[df["year"].isin(train_years)].reset_index(drop=True)
    test = df[df["year"].isin(test_years)].reset_index(drop=True)
    dev = df[df["year"].isin(dev_years)].reset_index(drop=True)

    print("Train years:", len(train_years), "| rows:", len(train))
    print("Test years:", len(test_years), "| rows:", len(test))
    print("Dev years:", len(dev_years), "| rows:", len(dev))

    train.to_csv(os.path.join(RELATIONS_PATH, "../train.csv"), index=False)
    test.to_csv(os.path.join(RELATIONS_PATH, "../test.csv"), index=False)
    dev.to_csv(os.path.join(RELATIONS_PATH, "../dev.csv"), index=False)


if __name__ == '__main__':
    extract_relations()
    create_dataset()
    split_dataset()