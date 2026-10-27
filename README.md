
# London Air Quality Data Pipeline

An incremental data engineering pipeline that extracts hourly air pollution measurements from the London Air Quality Network (LAQN), processes and validates the data, stores it in Parquet format, and presents the results through an interactive Streamlit dashboard.

The project investigates how nitrogen dioxide (NO₂) concentrations differ between roadside and urban background monitoring stations in London.

## 1. Project Overview

Air quality measurements are collected continuously across London, but monitoring stations vary in their pollutant coverage and data completeness.

The aim of this project was to build a reproducible pipeline capable of:

- Extracting historical hourly measurements from an external API.
- Processing multiple monitoring stations and pollutants.
- Updating previously collected data without creating duplicates.
- Reprocessing historical periods when measurements become available or are revised.
- Validating the stored dataset.
- Presenting air quality trends and data-quality limitations interactively.

## 2. Data Source

**Provider:** London Air Quality Network (LAQN), Imperial College London

**API documentation:** https://api.erg.ic.ac.uk/AirQuality/help

The pipeline uses the LAQN API to retrieve hourly measurements for selected stations.

| Station code | Monitoring station       | Classification   | Pollutants  |
| ------------ | ------------------------ | ---------------- | ----------- |
| BL0          | Camden - Bloomsbury      | Urban Background | NO₂, PM2.5 |
| KC1          | North Kensington         | Urban Background | NO₂, PM2.5 |
| GN4          | Greenwich - Fiveways A20 | Roadside         | NO₂        |
| HG1          | Haringey Town Hall       | Roadside         | NO₂        |

**Study period:** 1–21 May 2026.

Stations were selected after checking monitoring-site metadata and testing whether the API returned usable numerical measurements.

## 3. Pipeline Architecture

```text
LAQN API
   |
   v
Python extraction (requests)
   |
   v
Data cleaning and standardization (pandas)
   |
   v
Incremental merge and deduplication
   |
   v
Parquet storage (PyArrow)
   |
   +----> Automated validation
   |
   +----> Analysis and Streamlit dashboard
```

### Extraction

`extract.py` retrieves measurements in three-day batches, processing each station-pollutant combination independently.

The pipeline uses an incremental watermark based on the latest stored timestamp for each combination.

A two-day lookback allows recent measurements to be retrieved again in case the API has updated previously published values.

### Deduplication

Each measurement is identified by the composite key:

`(site_code, pollutant, timestamp)`

Incoming records are merged with existing data, and duplicates are removed.

Valid numerical readings are preferred over missing values. When both records contain valid readings, the incoming measurement takes precedence.

### Historical reprocessing

The extractor supports command-line date arguments, allowing older periods to be revisited without deleting newer records.

### Error handling

API requests use retry logic for temporary HTTP errors, including rate limiting and server failures.

If a batch fails after retries, the pipeline reports the affected station, pollutant, and date range, then stops rather than silently skipping the failed batch.

Successfully processed batches are saved incrementally.

## 4. Technologies

- **Python:** Pipeline implementation
- **Requests:** LAQN API extraction
- **pandas:** Cleaning, transformation, and analysis
- **PyArrow / Parquet:** Columnar data storage
- **Streamlit:** Interactive dashboard
- **Plotly:** Data visualization
- **Git:** Version control

## 5. Project Structure

```text
london-air-quality/
├── extract.py
├── validate.py
├── analyse.py
├── dashboard.py
├── explore_stations.py
├── check_pollutants.py
├── requirements.txt
├── .gitignore
├── README.md
└── data/
    └── processed/
        └── measurements.parquet   # Generated locally
```

The processed Parquet file is excluded from version control and can be regenerated using the extractor.

## 6. Installation and Usage

Clone the repository:

```bash
git clone <REPOSITORY_URL>
cd london-air-quality
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Run the extraction

Run the default extraction:

```bash
python extract.py
```

The default study period ends on 21 May 2026.

To extend the extraction end date:

```bash
python extract.py --end-date 2026-05-24
```

To reprocess an earlier period:

```bash
python extract.py --start-date 2026-05-10 --end-date 2026-05-12
```

### Validate the dataset

```bash
python validate.py
```

### Run the analysis

```bash
python analyse.py
```

### Launch the dashboard

```bash
streamlit run dashboard.py
```

The dashboard is normally available at `http://localhost:8501`.

## 7. Data Validation

The validation script checks:

- Required columns are present.
- The dataset is not empty.
- Station and pollutant identifiers are populated.
- Timestamps are valid.
- Measurement values use a numeric data type.
- No duplicate composite measurement keys exist.

Missing pollutant values are retained as nulls rather than replaced with zero.

### Results from the initial backfill

| Metric                         | Result |
| ------------------------------ | -----: |
| Stored records                 |  3,024 |
| Valid measurements             |  2,663 |
| Duplicate measurement keys     |      0 |
| Overall completeness           | 88.06% |
| Station-pollutant combinations |      6 |

The historical reprocessing test successfully revisited 10–12 May 2026 without increasing the number of unique records.

## 8. Analytical Findings

The dashboard focuses on NO₂ concentrations at roadside and urban background monitoring stations.

For the 1–21 May 2026 study period:

- HG1 (roadside) recorded an average NO₂ concentration of 22.07 µg/m³.
- KC1 (urban background) recorded an average of approximately 9.00 µg/m³.
- Matching readings by timestamp produced 502 comparable hourly observations.
- The average roadside-minus-background difference was 13.07 µg/m³.
- HG1 recorded higher NO₂ than KC1 during 98.01% of matched hours.

These findings describe the selected stations and study period. They do not establish that traffic alone caused the observed differences.

## 9. Dashboard

The Streamlit dashboard provides:

- Overview metrics and completeness indicators.
- A matched-hour roadside versus background comparison.
- Average pollutant concentrations by station.
- Hourly concentration patterns in London local time.
- Daily concentration trends.
- Data completeness reporting.
- Interactive station and pollutant filters.

Daily trends require at least 18 valid hourly readings per station-day. This is a project-defined analytical threshold rather than an official LAQN standard.

## 10. Limitations and Future Improvements

**Data availability:** Some monitoring stations return hourly timestamps without valid pollutant measurements. GN4, for example, had substantially lower NO₂ completeness than HG1.

**Incremental recovery:** The standard two-day lookback does not automatically recover older missing measurements. Historical reprocessing is available through the `--start-date` argument.

**Study period:** The dashboard currently uses a fixed May 2026 study window, even when the extractor is run for a longer period.

**Station comparability:** Different monitoring locations may be influenced by traffic, weather, geography, and other local sources.

**Future improvements:** Potential extensions include automatic gap detection, configurable dashboard dates, more extensive unit tests, and scheduled extraction.

## 11. Engineering Decisions

The project deliberately uses Parquet rather than a database server because the dataset is relatively small and the pipeline runs locally. Parquet provides compact columnar storage and integrates directly with pandas.

Three-day extraction batches reduce the amount of data affected by an individual request failure and allow progress to be saved incrementally.

A composite measurement key enables repeatable processing without duplicate records.

Missing readings remain null to preserve the distinction between unavailable measurements and actual zero concentrations.

These decisions prioritize simplicity, reproducibility, and data integrity while leaving room for future scaling.
