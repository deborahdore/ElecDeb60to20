#python3 src/remove_duplicate_components.py \
#    --folder data/annotations/relations/original/1960/3 \
#    --ann    data/annotations/relations/3_1960.ann


#python3 /Users/ddore/Documents/ElecDeb60to20/src/remap_component_ids.py \
#--folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/1960/3 \
#--ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/3_1960.ann \
#--max-distance 15 --dry-run

#python3 src/remove_duplicate_components.py \
#    --folder data/annotations/relations/original/1960/3 \
#    --ann    data/annotations/relations/3_1960.ann

#for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/1960/3/*.ann; do
#  python /Users/ddore/Documents/ElecDeb60to20/src/renumber_components.py --file "$f" --start 1000
#done

#python3 src/remove_duplicate_components.py \
#    --folder data/annotations/relations/original/1960/3 \
#    --ann    data/annotations/relations/3_1960.ann

python3 src/move_relations.py \
    --folder data/annotations/relations/original/1960/3 \
    --ann    data/annotations/relations/3_1960.ann


#python3 src/merge_different_type_components.py \
#    --folder data/annotations/relations/original/1960/3 \
#    --ann    data/annotations/relations/3_1960.ann \
#    --max-distance 5


#python3 /Users/ddore/Documents/ElecDeb60to20/src/verify_spans.py \
#    --ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/3_1960.ann \
#    --txt /Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/3_1960.txt

#for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/1960/3/*.ann; do
#  python /Users/ddore/Documents/ElecDeb60to20/src/fix_spans.py --ann "$f" --txt /Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/3_1960.txt
#done

#python /Users/ddore/Documents/ElecDeb60to20/src/renumber_components.py\
# --file "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/1960/3/1960_13Oct_1.ann" --start 534