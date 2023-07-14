# utilities to load data into BigQuery

```csv2gs.sh``` shell script export data from SQLite into CSV file, then upload to Google Cloud Storage bucket. The upload will trigger function in ```cloud_function``` directory which will load data into Big Query table.

```bq``` directory contains script to load CSV to BigQuery using CLI tool.

## create cloud function by CLI

```shell

gcloud functions deploy load_csv_to_bigquery \
  --runtime python310 \
  --trigger-event "projects/_/buckets/vinolab/topics/google.storage.object.finalize" \
  --source ./cloud_function \
  --entry-point load_csv_to_bigquery \
  --service-account "<service_account>@<project_id>.iam.gserviceaccount.com" \
  --project project_id


```
