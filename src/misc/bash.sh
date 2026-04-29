set -e

year=1960
number=1

#python3 remove_duplicate_components.py \
#    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/"$number" \
#    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/"$number"_$year.ann

#python renumber_components_folder.py --folder "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number" --start 1000

#for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number/*.ann; do
#  base=$(basename "$f" .ann)
#
#  python fix_spans.py \
#    --ann "$f" \
#    --txt "/Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/"$number"_$year.txt"
#done

#python3 remove_duplicate_components.py \
#    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/"$number" \
#    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/"$number"_$year.ann

#python remap_component_ids.py \
#--folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/"$number" \
#--ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/"$number"_$year.ann \
#--max-distance 5 --dry-run

#python3 remove_duplicate_components.py \
#    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/"$number" \
#    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/"$number"_$year.ann


#python3 remove_duplicate_components.py \
#    --folder data/annotations/relations/original/$year/"$number "\
#    --ann    data/annotations/relations/"$number_"$year.ann
#
## ================================================ SELECT STARTING NUMBER
#python renumber_components_folder.py --folder data/annotations/relations/original/$year/"$number "--start 0
#
#python3 move_components.py \
#    --folder data/annotations/relations/original/$year/"$number "\
#    --ann    data/annotations/relations/"$number_"$year.ann
#
#python3 move_relations.py \
#    --folder data/annotations/relations/original/$year/"$number "\
#    --ann    data/annotations/relations/"$number_"$year.ann
#
#python fix_spans.py --ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/"$number_"$year.ann \
#          --txt  /Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/"$number_"$year.txt
#
#python clean_ann.py --file /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/"$number_"$year.ann
