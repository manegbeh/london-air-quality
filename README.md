
# London Air Quality: Roadside vs Urban Background Pollution

### An Incremental Data Engineering Pipeline and Interactive Dashboard

A Python data engineering project using the London Air Quality Network (LAQN) API to explore differences in nitrogen dioxide (NO₂) concentrations between selected roadside and urban background monitoring stations.

The project combines incremental data extraction, validation, Parquet storage and an interactive Streamlit dashboard to investigate air quality patterns while making data availability and quality limitations visible.

**Primary question:** How do NO₂ concentrations differ between selected roadside and urban background monitoring stations in London?

**Study period:** 1–21 May 2026

**Data source:** [London Air Quality Network API](https://api.erg.ic.ac.uk/AirQuality/help)

---

## 1. Project Background and Objective

The London Air Quality Network provides measurements of air pollution collected from monitoring stations across London.

For this assessment, I was provided with the LAQN API and tasked with building a data pipeline using the available data.

Rather than attempting to analyze every station and pollutant, I narrowed the project to a specific question: how do nitrogen dioxide concentrations differ between selected roadside and urban background locations?

This focus allowed me to develop a pipeline around a clear analytical objective while demonstrating practical data engineering decisions, including incremental extraction, duplicate handling, data validation and reproducibility.

The project has two main components:

1. **Data engineering:** Building a repeatable pipeline to extract, process, validate and store hourly air quality measurements.
2. **Data presentation:** Developing an interactive dashboard to compare monitoring stations, investigate changes over time and understand data completeness.

The objective is not to establish the causes of pollution differences, but to provide a transparent and reproducible comparison using the available measurements.

---

## 2. Scope and Station Selection

### Monitoring Stations

The pipeline processes measurements from four monitoring stations:

| Station Code | Classification   | NO₂     | PM2.5        |
| ------------ | ---------------- | -------- | ------------ |
| BL0          | Urban Background | Included | Included     |
| KC1          | Urban Background | Included | Included     |
| GN4          | Roadside         | Included | Not included |
| HG1          | Roadside         | Included | Not included |

This produces six station-pollutant combinations.

### Why these stations?

During the initial exploration, I reviewed monitoring-site information and tested the availability of measurements across different stations and pollutants.

I selected these combinations because they returned usable measurements for the study period and allowed the pipeline to process more than one station and pollutant.

For the main comparison, I focused on HG1 and KC1 because both provided highly complete NO₂ datasets, allowing measurements to be matched by timestamp.

### Why focus on NO₂?

NO₂ provided a common pollutant for comparing the selected roadside and urban background stations.

This gave the analysis a more specific purpose than comparing unrelated pollutants or presenting every available measurement without a clear question.

### Why is roadside PM2.5 missing?

The final extraction configuration includes PM2.5 measurements for BL0 and KC1, but not for GN4 or HG1.

This reflects the station-pollutant combinations selected during initial API exploration.

The project has not established whether the selected roadside stations lack PM2.5 monitoring entirely, whether measurements were unavailable during the study period, or whether another roadside station could provide suitable coverage.

Therefore, the dashboard does not support a roadside versus urban background comparison for PM2.5.

PM2.5 remains available as a secondary exploration of the selected background stations, while the principal roadside comparison focuses on NO₂.

An important improvement would be to investigate additional roadside PM2.5 stations and extend the comparison where sufficient measurements are available.

---

## 3. Pipeline Architecture

```text
London Air Quality Network API
              |
              v
       Python Extraction
          (Requests)
              |
              v
    Incremental Watermarks
      + Two-Day Lookback
              |
              v
     Three-Day API Batches
              |
              v
    Cleaning and Processing
           (pandas)
              |
              v
   Deduplication and Merging
              |
              v
      Parquet Data Storage
              |
       +------+------+
       |             |
       v             v
   Validation     Analysis
       |             |
       |             v
       |        Streamlit +
       |          Plotly
       |             |
       +-------------+
                     |
                     v
           Interactive Dashboard
```

### Pipeline Responsibilities

The pipeline is responsible for:

- Retrieving hourly measurements from the LAQN API.
- Standardizing timestamps and numerical values.
- Processing individual station-pollutant combinations.
- Loading only relevant periods during subsequent runs.
- Reprocessing recently published measurements.
- Preventing duplicate records.
- Preserving missing measurements.
- Supporting historical backfills.
- Saving processed data in Parquet format.
- Validating the resulting dataset.

---

## 4. Technology Choices and Design Rationale

| Technology        | Purpose                     | Reason for Selection                                                                     |
| ----------------- | --------------------------- | ---------------------------------------------------------------------------------------- |
| Python            | Pipeline implementation     | Supports API integration, data processing and automation within one language             |
| Requests          | API extraction              | Provides HTTP requests, timeouts and retry integration                                   |
| pandas            | Transformation and analysis | Supports timestamp processing, missing values, deduplication and aggregation             |
| Parquet / PyArrow | Processed data storage      | Provides typed, columnar storage without requiring a database server                     |
| Streamlit         | Dashboard application       | Integrates directly with the Python pipeline and is straightforward to reproduce locally |
| Plotly            | Interactive visualization   | Supports hover information, filtering and interactive charts                             |
| Git / GitHub      | Version control             | Makes project changes traceable and the source code accessible                           |

### Why Streamlit instead of Tableau or Power BI?

I had previous experience with Tableau, but chose Streamlit because the project was built primarily in Python.

Streamlit allowed me to work directly with the processed Parquet dataset and reuse pandas calculations without introducing an additional reporting platform.

It also kept the application reproducible: another user can clone the repository, install the dependencies and launch the dashboard locally.

For a larger organization with established reporting infrastructure and a wider nontechnical audience, Tableau or Power BI could be more appropriate.

### Why Plotly?

I wanted users to explore measurements rather than rely entirely on static charts.

Plotly provides interactive tooltips and charts that integrate directly with Streamlit, making it easier to investigate individual values, time periods and station differences.

### Why Parquet rather than CSV or a database?

Parquet preserves data types and provides compact, columnar storage suitable for analytical processing.

The dataset is relatively small, so introducing a separate database server would add complexity without a clear requirement for concurrent users or transactional updates.

CSV would be simpler to inspect manually, but it does not preserve timestamp and numerical types as reliably.

If the project grew substantially, I would consider partitioned storage or a database depending on the access patterns and operational requirements.

---

## 5. Extraction Design and Engineering Decisions

### Incremental Extraction

Rather than downloading the entire historical dataset every time, the extractor identifies the latest stored timestamp for each station-pollutant combination.

That timestamp acts as a **watermark**, helping determine where extraction should resume.

**Why this decision?**

Repeatedly downloading unchanged historical measurements would introduce unnecessary API requests and processing.

Tracking watermarks separately also means that different station-pollutant combinations can progress independently.

### Two-Day Lookback

The pipeline revisits the two days preceding the latest stored timestamp.

**Why this decision?**

Measurements may be published late or corrected after their initial retrieval.

A lookback allows recently updated values to be fetched again rather than assuming all previous API responses are final.

**Limitation:** Corrections or missing data older than the lookback window are not automatically recovered.

### Three-Day Extraction Batches

Requests are processed in three-day date windows.

**Why this decision?**

Smaller requests make extraction easier to monitor and failures easier to isolate. The pipeline can also save successful batches incrementally.

Three days is a practical implementation choice, not a known LAQN API requirement.

### Retry Logic and Error Handling

HTTP requests use retry logic for temporary failures, including rate limiting and server errors.

Requests also have a timeout to prevent the pipeline from waiting indefinitely.

If retries are exhausted, extraction stops and reports the failed request rather than silently skipping the affected period.

**Why this decision?**

An external API is outside the pipeline's control. Temporary failures should be tolerated where possible, but persistent failures must remain visible.

### UTC Timestamp Standardization

Measurement timestamps are standardized to timezone-aware UTC values before storage.

**Why this decision?**

A consistent timezone makes measurements easier to order, merge, deduplicate and compare across stations.

The dashboard converts timestamps to London local time when analyzing patterns by hour of day, so daylight saving time is handled appropriately.

### Missing Values

Invalid or unavailable numerical measurements are stored as null values rather than replaced with zero.

**Why this decision?**

A missing reading is not equivalent to a genuine zero concentration.

Replacing missing values with zero would distort averages and hide data-quality problems.

### Deduplication

Measurements are uniquely identified by:

```python
["site_code", "pollutant", "timestamp"]
```

New observations are merged with previously stored measurements, and duplicate keys are removed.

Valid numerical measurements are preferred over missing values. When both versions contain a valid value, the incoming record takes precedence.

**Why this decision?**

Overlapping extraction windows are intentional, but overlapping records should not produce duplicate observations.

This approach supports repeatable processing and allows recently updated measurements to replace older versions.

### Historical Backfilling

The extractor accepts optional `--start-date` and `--end-date` arguments.

This allows historical periods to be reprocessed without deleting the existing dataset.

**Why this decision?**

A fixed lookback cannot automatically address every historical gap or correction. Explicit backfilling provides a practical recovery mechanism.

---

## 6. Data Validation

The `validate.py` script performs structural checks on the processed dataset.

These include:

- Confirming that the Parquet file exists.
- Checking that required columns are present.
- Verifying that the dataset is not empty.
- Checking that identifiers and timestamps are populated.
- Verifying timestamp and numerical data types.
- Ensuring there are no duplicate measurement keys.
- Reporting completeness for each station-pollutant combination.

### Fresh-Clone Extraction Results

The following results were reproduced from a new GitHub clone and Python virtual environment.

| Metric                         | Result |
| ------------------------------ | -----: |
| Total stored records           |  3,024 |
| Valid measurements             |  2,663 |
| Missing measurements           |    361 |
| Overall data completeness      | 88.06% |
| Duplicate measurement keys     |      0 |
| Station-pollutant combinations |      6 |

### Completeness by Station and Pollutant

| Station | Pollutant | Total | Valid | Completeness |
| ------- | --------- | ----: | ----: | -----------: |
| BL0     | NO₂      |   504 |   381 |       75.60% |
| BL0     | PM2.5     |   504 |   504 |      100.00% |
| GN4     | NO₂      |   504 |   271 |       53.77% |
| HG1     | NO₂      |   504 |   503 |       99.80% |
| KC1     | NO₂      |   504 |   503 |       99.80% |
| KC1     | PM2.5     |   504 |   502 |       99.60% |

All structural validation checks passed.

GN4's relatively low completeness is an important consideration when interpreting its average NO₂ concentration.

The pipeline was also tested by rerunning extraction and manually reprocessing 10–12 May 2026 without introducing duplicate measurement keys.

---

## 7. Dashboard Design and Analytical Focus

The dashboard was designed around a limited number of related questions rather than attempting to visualize every field available through the API.

The intended audience is someone exploring the relationship between monitoring location, measured pollutant concentrations and data quality.

### Dashboard Question 1: What data is available?

**Design choice:** Summary metrics at the top of the dashboard.

These provide an overview of measurement counts, monitoring stations and completeness.

The purpose is to establish the scope of the dataset before presenting comparisons.

### Dashboard Question 2: Which stations record higher average concentrations?

**Design choice:** A station comparison chart and summary table.

This makes differences between selected monitoring locations easier to compare than reading individual measurement records.

However, station averages should be interpreted alongside completeness because some stations have substantially more missing data than others.

### Dashboard Question 3: Does the roadside-background difference persist when comparing the same hours?

**Design choice:** A matched-hour comparison between HG1 and KC1.

The analysis joins observations by timestamp so both concentrations refer to the same hour.

This is preferable to relying solely on unmatched averages, particularly where stations have different measurement coverage.

### Dashboard Question 4: How do concentrations change throughout the day?

**Design choice:** An hourly pattern chart.

This highlights variations across the local day and allows users to investigate when concentrations are relatively higher or lower.

Timestamps are converted to London local time for this analysis.

### Dashboard Question 5: How do concentrations change across the study period?

**Design choice:** A daily trend chart.

Daily averages help communicate broader changes that are difficult to identify from thousands of individual hourly records.

A daily average is included only when the station has at least 18 valid hourly measurements for that day.

The 18-hour threshold is a project-defined analytical choice, not an official LAQN standard.

### Dashboard Question 6: Can these measurements be trusted equally?

**Design choice:** A dedicated data-quality section.

The completeness chart and table show where readings are missing.

This is important because a visually convincing chart can still be misleading if the underlying data coverage is poor.

### Why not include more charts?

I prioritized a focused set of visualizations that each answer a distinct question.

Additional charts would not automatically improve the analysis and could make the dashboard harder to navigate.

The design emphasizes clarity, comparability and transparency over the number of visualizations.

---

## 8. Analytical Findings

### Average NO₂ by Monitoring Station

| Station | Classification   | Mean NO₂ (µg/m³) | Completeness |
| ------- | ---------------- | ------------------: | -----------: |
| BL0     | Urban Background |               16.75 |       75.60% |
| GN4     | Roadside         |               21.83 |       53.77% |
| HG1     | Roadside         |               22.07 |       99.80% |
| KC1     | Urban Background |                9.00 |       99.80% |

### Matched-Hour Comparison: HG1 vs KC1

The primary comparison used HG1, a roadside monitoring station, and KC1, an urban background station.

Both stations provided highly complete NO₂ measurements.

| Metric                               |         Result |
| ------------------------------------ | -------------: |
| Matched hourly observations          |            502 |
| HG1 mean NO₂                        |  22.07 µg/m³ |
| KC1 mean NO₂                        |   8.99 µg/m³ |
| Mean hourly difference               | +13.07 µg/m³ |
| Hours where HG1 recorded higher NO₂ |         98.01% |

Across the selected study period, the roadside station recorded higher NO₂ concentrations than the background station for most matched hours.

### Hourly Patterns

The hourly analysis identified different peak average hours:

- **HG1:** 00:00 London local time.
- **KC1:** 07:00 London local time.

These patterns describe the observed measurements and should not be interpreted as evidence of a particular pollution source without further investigation.

### Weekday and Weekend Comparison

| Station | Weekday Mean NO₂ | Weekend Mean NO₂ |
| ------- | ----------------: | ----------------: |
| HG1     |     22.40 µg/m³ |     21.25 µg/m³ |
| KC1     |      9.34 µg/m³ |      8.14 µg/m³ |

Both stations recorded slightly higher average concentrations during weekdays in the selected period.

### Interpretation

The results suggest a consistent difference between the two selected monitoring environments.

However, this is a descriptive comparison. HG1 and KC1 are located in different areas, and observed differences may reflect weather, traffic, other emission sources and local geography.

The analysis does not establish a causal relationship between roadside classification and NO₂ concentration.

---

## 9. Project Structure

```text
london-air-quality/
│
├── extract.py              # API extraction and incremental processing
├── validate.py             # Structural validation and completeness
├── analyse.py              # Analytical calculations and comparisons
├── dashboard.py            # Streamlit dashboard
├── explore_stations.py     # Monitoring station exploration
├── check_pollutants.py     # Pollutant availability exploration
│
├── requirements.txt        # Python dependencies
├── README.md               # Documentation
├── .gitignore
│
└── data/
    └── processed/
        └── measurements.parquet  # Generated locally
```

Generated Parquet data is excluded from Git so that the dataset can be recreated from the source API.

The exploration scripts are included to document the work undertaken to examine stations and pollutant availability.

---

## 10. Installation and Reproduction

### Clone the repository

```bash
git clone https://github.com/manegbeh/london-air-quality.git
cd london-air-quality
```

### Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
python -m pip install -r requirements.txt
```

### Extract measurements

Run the default extraction:

```bash
python extract.py
```

The default extraction covers the study period ending on 21 May 2026.

To specify another end date:

```bash
python extract.py --end-date 2026-05-24
```

To reprocess an earlier date range:

```bash
python extract.py --start-date 2026-05-10 --end-date 2026-05-12
```

### Validate the processed dataset

```bash
python validate.py
```

### Run the analysis

```bash
python analyse.py
```

### Launch the interactive dashboard

```bash
streamlit run dashboard.py
```

Open the local URL displayed in the terminal, usually:

`http://localhost:8501`

**Note:** The dashboard is configured around the original 1–21 May 2026 study period. Extending extraction beyond this range does not automatically extend the dashboard's analytical window.

---

## 11. Reproducibility Testing

The repository was cloned into a separate directory and tested using a newly created Python virtual environment.

The following operations were completed successfully:

1. Installing dependencies from `requirements.txt`.
2. Extracting the dataset from the LAQN API.
3. Generating the processed Parquet file.
4. Running the structural validation checks.
5. Reproducing the matched-hour analytical findings.
6. Launching and interacting with the Streamlit dashboard.

The fresh extraction produced 3,024 records, 2,663 valid measurements and no duplicate keys.

The matched-hour analysis reproduced 502 matched observations and a mean HG1-minus-KC1 difference of approximately 13.07 µg/m³.

This test helped confirm that the project does not depend on the original development environment or an existing local dataset.

---

## 12. Limitations

### Incomplete Station Coverage

The selected roadside stations do not have PM2.5 data in the final dataset, limiting cross-environment comparisons to NO₂.

The existing exploration was not exhaustive enough to establish whether alternative roadside PM2.5 sources would support an expanded comparison.

### Missing Measurements

Completeness varies considerably between monitoring stations.

GN4's NO₂ completeness was 53.77%, which makes comparisons involving that station less representative of the full study period.

### Limited Historical Gap Recovery

The incremental pipeline automatically revisits recent measurements but does not detect or recover all older missing data.

Historical reprocessing must currently be requested explicitly.

### Fixed Dashboard Study Period

The current dashboard focuses on May 1–21, 2026.

Measurements extracted outside that period are not automatically included in the dashboard.

### Descriptive Rather Than Causal Analysis

Observed concentration differences do not establish the causes of pollution.

Additional contextual data, including meteorological measurements and traffic information, would be necessary for a more detailed investigation.

### Storage and Scaling

The current implementation uses a local Parquet file, which suits the dataset size and development environment.

A larger-scale system might require partitioned datasets, more sophisticated data orchestration or a database suited to concurrent access.

---

## 13. Future Improvements

### Improve Pollutant Coverage

Explore additional roadside monitoring stations to identify suitable PM2.5 data and support a comparison across both station classifications.

### Add Automated Gap Detection

Detect missing historical timestamps and automatically schedule reprocessing for incomplete periods.

### Expand Dashboard Filtering

Allow users to choose their own study dates rather than relying on a fixed analytical window.

### Introduce Automated Tests

Add unit tests for parsing, deduplication, timestamp processing, missing-value handling and incremental extraction.

### Add Scheduled Execution

Schedule extraction to run automatically and report whether each update completed successfully.

### Investigate Environmental Context

Incorporate additional data, such as weather or traffic, to help explain changes in air quality without overinterpreting the existing measurements.

---

## 14. Key Engineering Lessons

This project reinforced that building a data pipeline involves more than retrieving and storing records.

Some of the most important decisions concerned what to do when data was missing, how to handle updated measurements, how to make repeated execution safe, and how to communicate limitations to someone using the final dashboard.

The exploratory work also demonstrated the importance of defining a clear analytical objective. Although the API exposed multiple stations and pollutants, narrowing the primary analysis to NO₂ allowed me to build a more coherent comparison.

The most valuable outcome was a pipeline that could be rerun from a fresh environment and produce consistent results, together with a dashboard that made the data and its limitations accessible.

---

**Repository:** https://github.com/manegbeh/london-air-quality

**Data provider:** London Air Quality Network, Imperial College London.
