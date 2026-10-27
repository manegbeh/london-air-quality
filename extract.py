
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# Configuration
# --------------------------------------------------

parser = argparse.ArgumentParser(
    description="Incremental London air quality data extraction"
)

parser.add_argument(
    "--start-date",
    type=date.fromisoformat,
    default=None,
    help="Optional start date for historical reprocessing (YYYY-MM-DD)"
)

parser.add_argument(
    "--end-date",
    type=date.fromisoformat,
    default=date(2026, 5, 21),
    help="Last date to extract (YYYY-MM-DD)"
)

args = parser.parse_args()

initial_date = date(2026, 5, 1)
backfill_end_date = args.end_date
batch_days = 3

output_path = Path("data/processed/measurements.parquet")
output_path.parent.mkdir(parents=True, exist_ok=True)

station_pollutants = [
    # Urban background
    {"site_code": "BL0", "pollutant": "NO2"},
    {"site_code": "BL0", "pollutant": "PM25"},
    {"site_code": "KC1", "pollutant": "NO2"},
    {"site_code": "KC1", "pollutant": "PM25"},

    # Roadside
    {"site_code": "GN4", "pollutant": "NO2"},
    {"site_code": "HG1", "pollutant": "NO2"},
]


# --------------------------------------------------
# API session with retry handling
# --------------------------------------------------

session = requests.Session()

retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)


# --------------------------------------------------
# Load existing data
# --------------------------------------------------

columns = ["site_code", "pollutant", "timestamp", "value"]

if output_path.exists():
    existing_df = pd.read_parquet(output_path)
    existing_df["timestamp"] = pd.to_datetime(
        existing_df["timestamp"],
        utc=True
    )
else:
    existing_df = pd.DataFrame(columns=columns)

print(f"Existing rows: {len(existing_df)}")


# --------------------------------------------------
# Determine extraction end date
# --------------------------------------------------

today = datetime.now(timezone.utc).date()

# End date is inclusive for the user.
# The extraction loop uses an exclusive upper bound.
end_date = min(
    backfill_end_date,
    today
) + timedelta(days=1)

if args.start_date is not None and args.start_date >= end_date:
    parser.error("--start-date must be on or before the extraction end date")


# --------------------------------------------------
# Extract each station-pollutant combination
# --------------------------------------------------

for station in station_pollutants:

    site_code = station["site_code"]
    pollutant = station["pollutant"]

    print(f"\nProcessing {site_code} - {pollutant}")

    # Find previously stored measurements for this stream.
    stream_df = existing_df[
        (existing_df["site_code"] == site_code)
        & (existing_df["pollutant"] == pollutant)
    ]

    if stream_df.empty:
        start_date = initial_date
    else:
        latest_timestamp = stream_df["timestamp"].max()

        # Revisit the last two days to capture revised readings.
        start_date = max(
            initial_date,
            latest_timestamp.date() - timedelta(days=2)
        )

    # An explicit start date overrides the automatic watermark.
    if args.start_date is not None:
        start_date = args.start_date

    if start_date >= end_date:
        print("No dates to process.")
        continue

    batch_start = start_date

    while batch_start < end_date:

        batch_end = min(
            batch_start + timedelta(days=batch_days),
            end_date
        )

        print(
            f"\nRequesting batch: "
            f"{batch_start} to {batch_end}"
        )

        start_formatted = batch_start.strftime("%d-%b-%Y")
        end_formatted = batch_end.strftime("%d-%b-%Y")

        url = (
            "https://api.erg.ic.ac.uk/AirQuality/Data/SiteSpecies/"
            f"SiteCode={site_code}/"
            f"SpeciesCode={pollutant}/"
            f"StartDate={start_formatted}/"
            f"EndDate={end_formatted}/Json"
        )

        # ------------------------------------------
        # Request data with error handling
        # ------------------------------------------

        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

        except (requests.RequestException, ValueError) as error:
            print(
                f"\nExtraction failed for {site_code} / {pollutant}"
                f"\nBatch: {batch_start} to {batch_end}"
                f"\nError: {error}"
            )
            raise

        # ------------------------------------------
        # Parse API response
        # ------------------------------------------

        raw_data = data.get("RawAQData", {})
        measurements = raw_data.get("Data", [])

        if measurements is None:
            measurements = []

        if isinstance(measurements, dict):
            measurements = [measurements]

        incoming_df = pd.DataFrame(measurements)

        if incoming_df.empty:
            print("No measurements returned.")
            batch_start = batch_end
            continue

        required_fields = [
            "@MeasurementDateGMT",
            "@Value"
        ]

        missing_fields = [
            field for field in required_fields
            if field not in incoming_df.columns
        ]

        if missing_fields:
            raise ValueError(
                f"Missing API fields for {site_code}/{pollutant}: "
                f"{missing_fields}"
            )

        # ------------------------------------------
        # Clean and standardize
        # ------------------------------------------

        incoming_df = incoming_df.rename(
            columns={
                "@MeasurementDateGMT": "timestamp",
                "@Value": "value"
            }
        )

        incoming_df = incoming_df[["timestamp", "value"]].copy()

        incoming_df["site_code"] = site_code
        incoming_df["pollutant"] = pollutant

        incoming_df["timestamp"] = pd.to_datetime(
            incoming_df["timestamp"],
            errors="coerce",
            utc=True
        )

        incoming_df["value"] = pd.to_numeric(
            incoming_df["value"],
            errors="coerce"
        )

        incoming_df = incoming_df.dropna(
            subset=["timestamp"]
        )

        # Keep only readings inside the requested batch.
        batch_start_utc = pd.Timestamp(
            batch_start,
            tz="UTC"
        )

        batch_end_utc = pd.Timestamp(
            batch_end,
            tz="UTC"
        )

        incoming_df = incoming_df[
            (incoming_df["timestamp"] >= batch_start_utc)
            & (incoming_df["timestamp"] < batch_end_utc)
        ].copy()

        incoming_df = incoming_df[columns]

        print(f"Incoming rows: {len(incoming_df)}")
        print(
            "Missing incoming values:",
            incoming_df["value"].isna().sum()
        )

        # ------------------------------------------
        # Merge and deduplicate
        # ------------------------------------------

        previous_count = len(existing_df)

        combined_df = pd.concat(
            [existing_df, incoming_df],
            ignore_index=True
        )

        # Prefer valid readings over missing readings.
        # When both are valid, the newer incoming row wins.
        combined_df["has_value"] = (
            combined_df["value"].notna()
        )

        combined_df = combined_df.sort_values(
            "has_value",
            kind="stable"
        )

        combined_df = combined_df.drop_duplicates(
            subset=["site_code", "pollutant", "timestamp"],
            keep="last"
        )

        combined_df = combined_df.drop(
            columns=["has_value"]
        )

        combined_df = combined_df.sort_values(
            ["site_code", "pollutant", "timestamp"]
        ).reset_index(drop=True)

        new_unique_rows = len(combined_df) - previous_count

        # ------------------------------------------
        # Save after each successful batch
        # ------------------------------------------

        combined_df.to_parquet(
            output_path,
            index=False
        )

        existing_df = combined_df.copy()

        print(f"New unique rows: {new_unique_rows}")
        print(f"Total stored rows: {len(existing_df)}")

        batch_start = batch_end

    print(f"Finished processing {site_code} - {pollutant}")


# --------------------------------------------------
# Final data validation
# --------------------------------------------------

print("\nFinal dataset summary:")

if existing_df.empty:
    print("No records stored.")

else:
    summary = existing_df.groupby(
        ["site_code", "pollutant"]
    ).agg(
        rows=("timestamp", "size"),
        first=("timestamp", "min"),
        last=("timestamp", "max"),
        missing=("value", lambda values: values.isna().sum())
    )

    print(summary)

    summary["completeness_pct"] = (
        (summary["rows"] - summary["missing"])
        / summary["rows"]
        * 100
    ).round(2)

    print("\nData completeness by pollutant:")
    print(
        summary[
            ["rows", "missing", "completeness_pct"]
        ]
    )

    duplicate_count = existing_df.duplicated(
        subset=["site_code", "pollutant", "timestamp"]
    ).sum()

    print(f"\nDuplicate keys: {duplicate_count}")
    print(f"Total stored records: {len(existing_df)}")

session.close()
