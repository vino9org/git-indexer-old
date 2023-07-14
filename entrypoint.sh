#!/bin/sh

if [ "$DATA_DIR" = "" ]; then
    DATA_DIR="/data/git-indexer"
fi

mkdir -p $DATA_DIR

if [ ! -d "/root/.ssh" ]; then
    # something is not right, let's wait for help
    sleep 7200
fi


if [ "$FILTER" = "" ]; then
    FILTER="*"
fi

PYTHONUNBUFFERED=1 python run.py --index --source gitlab --query "$QUERY" --filter "$FILTER" --upload --db $DATA_DIR/git-indexer.db --export-csv /tmp/all_commit_data.csv
