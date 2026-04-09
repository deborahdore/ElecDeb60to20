import hashlib
import os

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


if __name__ == '__main__':
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
            for entity in sorted(entities.values(), key=lambda e: int(e.id[1:])):
                unique_id = year + "_" + \
                            get_hash(entity.id + entity.text + entity.type + str(entity.span[0][0]) + str(
                                entity.span[0][-1]))
                id_to_unique_id[entity.id] = unique_id

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
                    "relation_class": relation.type,
                    "year": year
                })

        save_to_csv(os.path.join(COMPONENTS_PATH, year + ".csv"), year_components)
        save_to_csv(os.path.join(RELATIONS_PATH, year + ".csv"), year_relations)

        component_dataset.extend(year_components)
        relation_dataset.extend(year_relations)

    save_to_csv(os.path.join(COMPONENTS_PATH, "../components.csv"), component_dataset)
    save_to_csv(os.path.join(RELATIONS_PATH, "../relations.csv"), relation_dataset)
