set -e
number=3
year=1960

python fix_spans.py --ann "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann" \
    --txt "/Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/${number}_${year}.txt"

for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number/*.ann; do
  python fix_spans.py --ann "$f" \
    --txt "/Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/${number}_${year}.txt"
done
python3 remove_duplicate_components.py \
    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/"$number" \
    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann

python renumber_components_folder.py --folder "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number" --start 5000

python remap_component_ids.py \
        --folder "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number" \
        --ann "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann" \
        --max-distance 100 --dry-run

python3 remove_duplicate_components.py \
    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/"$number" \
    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann

## ================================================ SELECT STARTING NUMBER
#python renumber_components_folder.py --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number --start 503
##
#python3 move_components.py \
#    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number \
#    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann
##
#python3 move_relations.py \
#    --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number \
#    --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann
#
#python fix_spans.py --ann /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann \
#          --txt  /Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/${number}_${year}.txt
