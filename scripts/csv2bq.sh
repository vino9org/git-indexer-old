#! /bin/bash

set -e

csv2bq() {
    file=$1

    if [ ! -f "$file.csv" ]; then
        echo "File $file does not exists."
        exit -1
    fi

    echo uploading $1.csv to bigquery

    gsutil cp $file.csv gs://vinolab/$file.csv

    bq rm -f -t dev1.$file
    bq load --autodetect --source_format=CSV dev1.$file gs://vinolab/$file.csv

    # rm -rf $file.csv

}


sqlite_to_csv()
{
# bigquery cannot handle csv exported by sqlite3. commit message that span multiple lines is the problem
sqlite3 $1 <<EOF

.headers on
.mode csv

.output all_commit_data.csv
select * from all_commit_data;

.quit
EOF
}


pg_to_csv()
{
CWD=$(pwd)

psql sbc <<EOF

COPY (select * from all_commit_data) TO '$CWD/all_commit_data.csv'  WITH DELIMITER ',' CSV HEADER;

EOF
}

pg_to_csv
# csv2bq all_commit_data


