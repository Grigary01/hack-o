#!/bin/sh
set -eu

python -m scripts.migrate_db
python -m scripts.seed_demo

exec "$@"
