set -e

for year_path in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/*/; do
  [ -d "$year_path" ] || continue
  year=$(basename "$year_path")

  for number_path in "$year_path"*/; do
    [ -d "$number_path" ] || continue
    number=$(basename "$number_path")

  touch "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann"

  for f in /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number/*.ann; do
    python fix_spans.py --ann "$f" \
      --txt "/Users/ddore/Documents/ElecDeb60to20/data/annotations/txt/${number}_${year}.txt"
  done

  python renumber_components_folder.py --folder "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number" --start 1

  python3 move_components.py \
      --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number \
      --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann

  python3 move_relations.py \
      --folder /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/$year/$number \
      --ann    /Users/ddore/Documents/ElecDeb60to20/data/annotations/relations/${number}_${year}.ann

  done
done