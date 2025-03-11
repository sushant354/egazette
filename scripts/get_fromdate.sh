#!/bin/bash

usage="USAGE: $0 <source> [<output_file>]"
src_name=$1
[[ $src_name == '' ]] && echo "ERROR: missing <source> argument" && echo $usage && exit 1

output_file=$2

set -Eeuo pipefail

echo "got source: $src_name"

echo "getting identifier prefix"
to_sandox_val='False'
if [[ $TESTING == '1' ]]; then
  to_sandox_val='True'
fi
prefix=$(uv run python -c "from srcs.datasrcs_info import get_prefix; print(get_prefix('$src_name', to_sandbox=$to_sandox_val))")
echo "got prefix as: $prefix"
[[ $prefix != '' ]] || exit 1

echo "getting items with prefix from internet archive"
last_id=$(uvx --from internetarchive ia search $prefix --sort 'date asc' -i | tail -1)
echo "got last id as: $last_id"

if [[ $last_id == '' ]]; then
  echo "getting from date from config"
  from_date=$(uv run python -c "from srcs.datasrcs_info import get_start_date; d = get_start_date('$src_name'); print('' if d is None else d.strftime('%d-%m-%Y'))")
else
  echo "getting from date from the last id"
  from_date=$(uvx --from internetarchive ia metadata $last_id | jq -r .metadata.date | awk -v FS=- -v OFS=- '{print $3,$2,$1}')
fi
echo "got from date as: $from_date"
[[ $from_date != '' ]] || exit 1

[[ $output_file == '' ]] && exit 0

echo "$from_date" > $output_file


