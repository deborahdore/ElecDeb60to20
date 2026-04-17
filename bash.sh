#python3 src/remove_duplicate_components.py \
#    --folder data/annotations/relations/original/1960/2 \
#    --ann    data/annotations/relations/2_1960.ann


#python3 /Users/ddore/Documents/ElecDeb60to20/src/remap_component_ids.py \
#--folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/1960/2 \
#--ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/2_1960.ann \
#--max-distance 5 --dry-run

#python3 src/remove_duplicate_components.py \
#    --folder data/annotations/relations/original/1960/2 \
#    --ann    data/annotations/relations/2_1960.ann

#for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/original/1960/2/*.ann; do
#  python /Users/ddore/Documents/ElecDeb60to20/src/renumber_components.py --file "$f" --start 1000
#done

#python3 src/remove_duplicate_components.py \
#    --folder data/annotations/relations/original/1960/2 \
#    --ann    data/annotations/relations/2_1960.ann

python3 src/move_relations.py \
    --folder data/annotations/relations/original/1960/2 \
    --ann    data/annotations/relations/2_1960.ann


#python3 src/merge_different_type_components.py \
#    --folder data/annotations/relations/original/1960/2 \
#    --ann    data/annotations/relations/2_1960.ann \
#    --max-distance 5