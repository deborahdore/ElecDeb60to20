import os
import random

import pandas as pd
import rootutils
from brat_parser import get_entities_relations_attributes_groups

rootutils.setup_root(__file__, indicator=".project-root", pythonpath=True, cwd=True)

# def fix_equivalent_relations(files):
#     f in files:
#     input_file = os.path.join(ann_relations_path, f)
#     with open(input_file, "r", encoding="utf-8") as f:
#         lines = [line.rstrip() for line in f]
#
#     # Separate normal lines and * Equivalent lines
#     normal_lines = []
#     equivalent_lines = []
#     for line in lines:
#         if line.startswith("*"):
#             equivalent_lines.append(line)
#         else:
#             normal_lines.append(line)
#
#     # Find the last R index
#     r_indices = [int(m.group(1)) for l in normal_lines
#                  if (m := re.match(r"R(\d+)\s", l))]
#     next_r_idx = max(r_indices, default=0) + 1
#
#     # Convert * Equivalent lines into R-style lines
#     new_r_lines = []
#     for eq_line in equivalent_lines:
#         # eq_line example: "*\tEquivalent T672 T671 T1"
#         parts = eq_line.split()
#         if len(parts) >= 3:
#             label = parts[1]  # 'Equivalent'
#             t_ids = parts[2:]  # ['T672', 'T671', 'T1', ...]
#             # Generate consecutive R lines
#             for i in range(1, len(t_ids)):
#                 arg1 = t_ids[0]
#                 arg2 = t_ids[i]
#                 new_r_lines.append(f"R{next_r_idx}\t{label} Arg1:{arg1} Arg2:{arg2}")
#                 next_r_idx += 1
#
#     # Combine normal lines + new R lines
#     all_lines = normal_lines + new_r_lines
#
#     # Write output
#     with open(input_file, "w", encoding="utf-8") as f:
#         for line in all_lines:
#             f.write(line + "\n")


if __name__ == '__main__':
    ann_relations_path = "./data/annotations/relations"
    files = sorted(f for f in os.listdir(ann_relations_path) if f.endswith(".ann"))

    df_relations = []
    for f in files:
        entities, relations, _, _ = get_entities_relations_attributes_groups(os.path.join(ann_relations_path, f))
        for relation in relations.values():
            arg1 = entities.get(relation.subj)
            arg2 = entities.get(relation.obj)
            rel_type = relation.type

            df_relations.append({
                "date": f.split("_")[1] + "_" + f.split("_")[0],
                "relation": True,
                "relation_type": rel_type,
                "subject": arg1.text,
                "subject_type": arg1.type,
                "object": arg2.text,
                "object_type": arg2.type
            })

    df_relations = pd.DataFrame(df_relations).dropna().reset_index(drop=True)
    os.makedirs("data/relations/", exist_ok=True)

    df_relations.to_csv("./data/relations/filtered_relations.csv", index=False)
    df_relations = df_relations[df_relations['relation_type'] != "Equivalent"].reset_index(drop=True)

    df_subject = df_relations[['date', 'subject', 'subject_type']].values.tolist()
    df_object = df_relations[['date', 'object', 'object_type']].values.tolist()

    # Create a set of existing (subject, object, date) tuples for quick lookup
    existing_pairs = set(zip(df_relations['subject'], df_relations['object'], df_relations['date']))

    new_relations = []

    while len(new_relations) < len(df_relations):
        arg_subject = random.choice(df_subject)

        # Filter objects to match the same date
        same_date_objects = [obj for obj in df_object if obj[0] == arg_subject[0]]
        if not same_date_objects:
            continue  # skip if no object with same date

        arg_object = random.choice(same_date_objects)

        # Skip if this pair exists in the original dataframe for the same date
        if (arg_subject[1], arg_object[1], arg_subject[0]) in existing_pairs:
            continue

        new_relation = {
            "date": arg_subject[0],
            "relation": False,
            "relation_type": "no_relation",
            "subject": arg_subject[1],
            "subject_type": arg_subject[2],
            "object": arg_object[1],
            "object_type": arg_object[2],
        }

        new_relations.append(new_relation)

    df_relations = pd.concat([df_relations, pd.DataFrame(new_relations)], axis=0,
                             ignore_index=True).dropna().reset_index(drop=True)
    print("Dataframe with false relations: ", len(df_relations))
    df_relations.to_csv("./data/relations/relations.csv", index=False)

    dates = list(set(df_relations["date"].tolist()))
    total = len(dates)
    random.seed(123)

    train_size = int(total * 0.7)
    test_size = int(total * 0.2)

    train = random.sample(dates, train_size)
    remaining = [d for d in dates if d not in train]

    test = random.sample(remaining, test_size)
    dev = [d for d in remaining if d not in test]

    # convert to sets if needed
    train_set = set(train)
    test_set = set(test)
    dev_set = set(dev)

    print("Train dates:", len(train_set))
    print("Test dates:", len(test_set))
    print("Dev dates:", len(dev_set))

    train = df_relations[df_relations["date"].isin(train_set)]
    test = df_relations[df_relations["date"].isin(test_set)]
    dev = df_relations[df_relations["date"].isin(dev_set)]

    print("Len train:", len(train))
    print("Len test:", len(test))
    print("Len dev:", len(dev))

    train.to_csv("data/relations/train.csv", index=False)
    test.to_csv("data/relations/test.csv", index=False)
    dev.to_csv("data/relations/dev.csv", index=False)
