from pathlib import Path
import pandas as pd

path = Path("data/processed/measurements.parquet")

if not path.exists():
    raise FileNotFoundError("Processed dataset does not exist")

df = pd.read_parquet(path)

required_columns = {
    "site_code",
    "pollutant",
    "timestamp",
    "value"
}

assert required_columns.issubset(df.columns), (
    "Required columns are missing"
)

assert not df.empty, "Dataset is empty"

assert df["site_code"].notna().all(), (
    "Missing station codes detected"
)

assert df["pollutant"].notna().all(), (
    "Missing pollutant codes detected"
)

assert df["timestamp"].notna().all(), (
    "Missing timestamps detected"
)

assert pd.api.types.is_datetime64_any_dtype(
    df["timestamp"]
), "Timestamp column is not datetime"

assert pd.api.types.is_numeric_dtype(
    df["value"]
), "Measurement values are not numeric"

keys = ["site_code", "pollutant", "timestamp"]

assert not df.duplicated(subset=keys).any(), (
    "Duplicate measurement keys detected"
)

print("All structural validation checks passed.")
print(f"Total records: {len(df)}")

summary = df.groupby(
    ["site_code", "pollutant"]
).agg(
    total=("value", "size"),
    valid=("value", "count")
)

summary["completeness_pct"] = (
    summary["valid"] / summary["total"] * 100
).round(2)

print("\nData completeness:")
print(summary.to_string())