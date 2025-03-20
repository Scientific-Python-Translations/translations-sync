#!/usr/bin/env bash

if [ -z "$1" ]; then
    echo "Usage: $0 <language_code>"
    exit 1
fi

language_code=$1
script_location=$(dirname "$0")

language_name=$(python3 -c "
import sys
sys.path.insert(0, '$script_location')
from git_tools import language_code_map
print(language_code_map.get('$language_code', ''))
")

if [ -z "$language_name" ]; then
    echo "get_language_name: language code $language_code not recognized." >&2
    exit 1
fi

echo "$language_name"
