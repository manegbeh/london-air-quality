import pandas as pd

df = pd.read_parquet(
    "data/processed/measurements.parquet"
)

no2 = df[
    (df["pollutant"] == "NO2")
    & (df["timestamp"] >= "2026-05-01")
    & (df["timestamp"] < "2026-05-22")
].copy()

station_types = {
    "BL0": "Urban Background",
    "KC1": "Urban Background",
    "GN4": "Roadside",
    "HG1": "Roadside"
}

no2["site_type"] = no2["site_code"].map(station_types)

summary = no2.groupby(
    ["site_code", "site_type"]
).agg(
    total_hours=("value", "size"),
    valid_hours=("value", "count"),
    mean_no2=("value", "mean"),
    median_no2=("value", "median")
).reset_index()

summary["completeness_pct"] = (
    summary["valid_hours"]
    / summary["total_hours"]
    * 100
).round(2)

print(summary.round(2).to_string(index=False))
paired = no2[
    no2["site_code"].isin(["HG1", "KC1"])
].pivot_table(
    index="timestamp",
    columns="site_code",
    values="value"
)

paired = paired.dropna(subset=["HG1", "KC1"])

paired["difference"] = paired["HG1"] - paired["KC1"]

print("\nPaired hourly comparison:")
print("Matched hours:", len(paired))
print("HG1 mean:", round(paired["HG1"].mean(), 2))
print("KC1 mean:", round(paired["KC1"].mean(), 2))
print("Mean difference:", round(paired["difference"].mean(), 2))

print(
    "Hours with higher roadside NO2:",
    round((paired["difference"] > 0).mean() * 100, 2),
    "%"
)

hourly = paired[["HG1", "KC1"]].copy()

# LAQN timestamps are in GMT/UTC.
# Convert to London local time for interpreting daily patterns.
hourly.index = hourly.index.tz_convert("Europe/London")

hourly["hour"] = hourly.index.hour

hourly_pattern = hourly.groupby("hour")[
    ["HG1", "KC1"]
].mean().round(2)

print("\nAverage NO2 by hour of day:")
print(hourly_pattern.to_string())

print("\nPeak hour for HG1:", hourly_pattern["HG1"].idxmax())
print("Peak hour for KC1:", hourly_pattern["KC1"].idxmax())

hourly["day_of_week"] = hourly.index.day_of_week

hourly["day_type"] = hourly["day_of_week"].apply(
    lambda day: "Weekday" if day < 5 else "Weekend"
)

day_type_summary = hourly.groupby("day_type")[
    ["HG1", "KC1"]
].agg(["mean", "count"]).round(2)

print("\nWeekday vs weekend NO2:")
print(day_type_summary.to_string())