import pandas as pd

if __name__ == '__main__':

    df = pd.read_json("./1_1960.json")
    ann_file = "./1_1960"
    read_file = [line.rstrip("\n") for line in open(f"{ann_file}.txt", "r", encoding="utf-8")]

    full_text = "\n".join(read_file) + "\n"

    # 2. Precompute starting offsets for each ID
    offsets = {}
    running_offset = 0
    for i, line in enumerate(read_file, start=1):
        offsets[i] = running_offset
        running_offset += len(line) + 1  # +1 for newline

    label_idx = 1

    with open(f"{ann_file}.ann", "w", encoding="utf-8") as ann_file:
        for _, row in df.iterrows():
            speech_id = row['inner_id']
            speech_text = row['data']['text']
            labels = row['annotations'][0]['result']

            # absolute base offset for this speech block
            base_offset = offsets[speech_id]

            for label in labels:
                rel_start = int(label['value']["start"])
                rel_end = int(label['value']["end"])
                abs_start = base_offset + rel_start
                abs_end = base_offset + rel_end
                label_text = label['value']["text"]
                label_type = label['value']["labels"][0]

                ann_file.write(
                    f"T{label_idx}\t{label_type} {abs_start} {abs_end}\t{label_text}\n"
                )
                label_idx += 1
