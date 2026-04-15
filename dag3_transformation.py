"""
Author: [Augustine Ugbeda]

"""

from datetime import datetime
from airflow import DAG
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator

# DAG default arguments
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}
# Define project, dataset, and table details
project_id = 'project-a2b19e0f-875f-4bb9-9e1'
dataset_id = 'staging_dataset'
transform_dataset_id = 'transform_dataset'

source_table = f'{project_id}.{dataset_id}.global_data'  # Main table loaded from CSV
countries = ['USA', 'Nigeria', 'Germany', 'Japan', 'France', 'Canada', 'Italy']  # Country-specific tables to be created

# DAG definition
with DAG(
    dag_id='load_and_transform',
    default_args=default_args,
    description='Load a CSV file from GCS to BigQuery and create country-specific tables',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['bigquery', 'gcs', 'csv'],
) as dag:

    # Task 1: Check if the file exists in GCS
    check_file_exists = GCSObjectExistenceSensor(
        task_id='check_file_exists',
        bucket='bkt_src_global_data',  # Replace with your bucket name
        object='global_health_data.csv',  # Replace with the file path in the bucket
        timeout=300,  # Maximum wait time in seconds
        poke_interval=30,  # Time interval in seconds to check again
        mode='poke',
    )

    # Task 2: Load CSV from GCS to BigQuery
    load_csv_to_bigquery = GCSToBigQueryOperator(
        task_id='load_csv_to_bq',
        bucket='bkt_src_global_data',  # Replace with your bucket name
        source_objects=['global_health_data.csv'],  # Path to your file in the bucket
        destination_project_dataset_table=source_table,
        source_format='CSV',
        allow_jagged_rows=True,
        ignore_unknown_values=True,
        write_disposition='WRITE_TRUNCATE',  # Options: WRITE_TRUNCATE, WRITE_APPEND, WRITE_EMPTY
        skip_leading_rows=1,  # Skip header row
        field_delimiter=',',
        autodetect=True,
    )

    # Tasks 3: Create country-specific tables
    for country in countries:
        BigQueryInsertJobOperator(
            task_id=f'create_table_{country.lower()}',
            configuration={
                "query": {
                    "query": f"""
                        CREATE OR REPLACE TABLE `{project_id}.{transform_dataset_id}.{country.lower()}_table` AS
                        SELECT *
                        FROM `{source_table}`
                        WHERE country = '{country}'
                    """,
                    "useLegacySql": False,  # Use standard SQL syntax
                }
            },
        ).set_upstream(load_csv_to_bigquery)

    # Define task dependencies
    check_file_exists >> load_csv_to_bigquery
