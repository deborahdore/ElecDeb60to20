set -e

python3 remove_duplicate_components.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann

for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/2020/46/*.ann; do
  python /Users/ddore/Documents/ElecDeb60to20/renumber_components.py --file "$f" --start 1000
done

python remap_component_ids.py \
--folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/2020/46 \
--ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/46_2020.ann \
--max-distance 5

python3 remove_duplicate_components.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann

python remap_component_ids.py \
--folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/2020/46 \
--ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/46_2020.ann \
--max-distance 15 --dry-run

python3 remove_duplicate_components.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann

python3 merge_different_type_components.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann \
    --max-distance 5

python3 remove_duplicate_components.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann

# ================================================ SELECT STARTING NUMBER
python renumber_components_folder.py --folder data/annotations/relations/original/2020/46 --start 0

python3 move_components.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann

python3 move_relations.py \
    --folder data/annotations/relations/original/2020/46 \
    --ann    data/annotations/relations/46_2020.ann

python fix_spans.py --ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/46_2020.ann \
          --txt  /Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/46_2020.txt

python clean_ann.py --file /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/46_2020.ann
