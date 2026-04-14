# ELT-Data-Pipeline-with-GCP-and-Airflow
This project demonstrates a production-style **ELT (Extract, Load, Transform)** pipeline
built with **Apache Airflow** and **Google Cloud Platform (GCP)**. It processes global
health data (1M+ records), loading it from Cloud Storage into BigQuery and transforming
it into country-specific tables and reporting views — built up across three progressive DAGs.

---
## Architecture Overview

<img width="1024" height="1536" alt="architecture" src="https://github.com/user-attachments/assets/cd027485-6208-49f9-b66a-297c00a54a99" />

### Data Layers

| Layer | Dataset | Description |
|---|---|---|
| Staging | `staging_dataset` | Raw data loaded directly from CSV |
| Transform | `transform_dataset` | Country-filtered tables |
| Reporting | `reporting_dataset` | Views with selected columns, filtered for analysis |

---

## DAGs — Progressive Build

This pipeline is built across **three DAGs**, each adding a layer of complexity.

---

### DAG 1 — `load_gcs_to_bq`

**Purpose:** Load a CSV file from GCS directly into a BigQuery staging table.

**Key operator:** `GCSToBigQueryOperator`
This is the foundation. It reads `global_health_data.csv` from the
`bkt_src_global_data` bucket and loads it into
`staging_dataset.global_data` with schema autodetection and WRITE_TRUNCATE
disposition.

```python
load_csv_to_bigquery = GCSToBigQueryOperator(
    task_id='load_csv_to_bq',
    bucket='bkt_src_global_data',
    source_objects=['global_health_data.csv'],
    destination_project_dataset_table='<project_id>.staging_dataset.global_data',
    source_format='CSV',
    write_disposition='WRITE_TRUNCATE',
    skip_leading_rows=1,
    autodetect=True,
)
```

---

### DAG 2 — `check_load_csv_to_bigquery`
The sensor polls GCS every 30 seconds (up to 5 minutes) before triggering
the load. If the file isn't found within the timeout, the DAG fails gracefully
rather than attempting a load on a missing object.

```python
check_file_exists = GCSObjectExistenceSensor(
    task_id='check_file_exists',
    bucket='bkt_src_global_data',
    object='global_health_data.csv',
    timeout=300,
    poke_interval=30,
    mode='poke',
)

check_file_exists >> load_csv_to_bigquery
```

---

### DAG 3 — `load_and_transform` (Transform Layer)

**Purpose:** Extends DAG 2 to partition the global staging table into
country-specific tables inside `transform_dataset`.

**New operator:** `BigQueryInsertJobOperator`
For each country, a `CREATE OR REPLACE TABLE` query filters the staging
table by the `country` column:

```python
countries = ['USA', 'Nigeria', 'Germany', 'Japan', 'France', 'Canada', 'Italy']

for country in countries:
    BigQueryInsertJobOperator(
        task_id=f'create_table_{country.lower()}',
        configuration={
            "query": {
                "query": f"""
                    CREATE OR REPLACE TABLE `{project_id}.transform_dataset.{country.lower()}_table` AS
                    SELECT * FROM `{project_id}.staging_dataset.global_data`
                    WHERE country = '{country}'
                """,
                "useLegacySql": False,
            }
        },
    ).set_upstream(load_csv_to_bigquery)
```

---

### DAG 4 — `load_and_transform_view` (Full Pipeline)

**Purpose:** The complete end-to-end pipeline. Adds a reporting layer on top
of the transform layer — creating a **view** for each country that surfaces
only disease-related columns where no vaccine or treatment is available.

**Purpose:** Adds a file existence check before loading, making the pipeline
resilient to missing source files.

**New operator:** `GCSObjectExistenceSensor`
Each view selects the following columns from its country table, filtered
where `Availability of Vaccines Treatment = False`:

- `year`
- `disease_name`
- `disease_category`
- `prevalence_rate`
- `incidence_rate`

```python
create_view_task = BigQueryInsertJobOperator(
    task_id=f'create_view_{country.lower()}_table',
    configuration={
        "query": {
            "query": f"""
                CREATE OR REPLACE VIEW `{project_id}.reporting_dataset.{country.lower()}_view` AS
                SELECT
                    `Year` AS year,
                    `Disease Name` AS disease_name,
                    `Disease Category` AS disease_category,
                    `Prevalence Rate` AS prevalence_rate,
                    `Incidence Rate` AS incidence_rate
                FROM `{project_id}.transform_dataset.{country.lower()}_table`
                WHERE `Availability of Vaccines Treatment` = False
            """,
            "useLegacySql": False,
        }
    },
)
```

A final `EmptyOperator` (`success_task`) acts as a convergence point,
confirming all 14 downstream tasks (7 tables + 7 views) completed successfully.

---

## Project Structure
<img width="1281" height="884" alt="load_and_transform_view-graph" src="https://github.com/user-attachments/assets/7cfabedb-b13a-48a5-93af-b7c97deac2ef" />

---

## GCP Resources

| Resource | Name |
|---|---|
| GCS Bucket | `bkt_src_global_data` |
| Source File | `global_health_data.csv` |
| Staging Table | `staging_dataset.global_data` |
| Transform Tables | `transform_dataset.<country>_table` |
| Reporting Views | `reporting_dataset.<country>_view` |

Countries covered: `USA`, `Nigeria`, `Germany`, `Japan`, `France`, `Canada`, `Italy`

---

## Requirements

- Google Cloud Platform project with BigQuery and Cloud Storage enabled
- Service account with BigQuery Data Editor + GCS Object Viewer permissions
- Apache Airflow with `apache-airflow-providers-google` installed
- Airflow GCP connection configured (default: `google_cloud_default`)



---

## Setup

1. Upload `global_health_data.csv` to the `bkt_src_global_data` GCS bucket
2. Create the three BigQuery datasets: `staging_dataset`, `transform_dataset`, `reporting_dataset`
2. Copy the DAG files into your Airflow `dags/` folder
4. Trigger `load_and_transform_view` (DAG 4) from the Airflow UI

---
## Sample Report
<img width="899" height="895" alt="image" src="https://github.com/user-attachments/assets/1e690631-6c3a-4045-a6c3-9058d885ecab" />



