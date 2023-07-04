#!/bin/sh

if [ "$DATA_DIR" = "" ]; then
    DATA_DIR="/data/git-indexer"
fi

mkdir -p $DATA_DIR

if [ ! -d "/root/.ssh" ]; then
    # something is not right, let's wait for help
    sleep 10000
fi


if [ "$FILTER" = "" ]; then
    FILTER="*"
fi

python run.py --index --source gitlab --query "$QUERY" --filter "$FILTER" --db --db $DATA_DIR/git-indexer.db