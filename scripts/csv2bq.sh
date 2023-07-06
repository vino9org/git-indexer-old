#! /bin/bash

set -e

csv2bq() {
    file=$1

    if [ ! -f "$file.csv" ]; then
        echo "File $file does not exists."
        exit -1
    fi

    echo uploading $1.csv to bigquery

    gsutil cp $file.csv gs://vinolab/$file.1.csv

    bq rm -f -t dev1.$file.1
    bq load --autodetect --source_format=CSV dev1.$file gs://vinolab/$file.csv

    # rm -rf $file.csv

}


sqlite_to_csv()
{
sqlite3 $1 <<EOF

.headers on
.mode csv

.output all_commit_data.csv
select * from all_commit_data ;

.quit
EOF
}

sqlite_to_csv $1
csv2bq all_commit_data


