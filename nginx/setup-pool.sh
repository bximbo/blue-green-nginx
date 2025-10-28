#!/bin/sh
set -e
POOL="${ACTIVE_POOL:-blue}"
if [ "$POOL" = "blue" ]; then
export BLUE_BACKUP=""
export GREEN_BACKUP="backup"
elif [ "$POOL" = "green" ]; then
export BLUE_BACKUP="backup"
export GREEN_BACKUP=""
else
echo "ERROR: ACTIVE_POOL must be blue or green" >&2
exit 1
fi