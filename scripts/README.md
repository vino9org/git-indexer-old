# utilities to load data into BigQuery

```csv2gs.sh``` shell script export data from SQLite into CSV file, then upload to Google Cloud Storage bucket. The upload will trigger function in ```cloud_function``` directory which will load data into Big Query table.

```bq``` directory contains script to load CSV to BigQuery using CLI tool.
