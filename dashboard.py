from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# --------------------------------------------------
# Page settings and configuration
# --------------------------------------------------

st.set_page_config(
    page_title="London Air Quality: Roadside vs Urban Background",
    page_icon="🌍",
    layout="wide"
)

STATION_METADATA = {
    "BL0": ("Camden - Bloomsbury", "Urban Background"),
    "KC1": ("North Kensington", "Urban Background"),
    "GN4": ("Greenwich - Fiveways A20", "Roadside"),
    "HG1": ("Haringey Town Hall", "Roadside"),
}

CONFIGURED_STREAMS = [
    ("BL0", "NO2"),
    ("BL0", "PM25"),
    ("KC1", "NO2"),
    ("KC1", "PM25"),
    ("GN4", "NO2"),
    ("HG1", "NO2"),
]

STUDY_START = pd.Timestamp("2026-05-01", tz="UTC")
STUDY_END = pd.Timestamp("2026-05-22", tz="UTC")

MIN_DAILY_HOURS = 18

POLLUTANT_LABELS = {
    "NO2": "NO₂",
    "PM25": "PM2.5",
}


# --------------------------------------------------
# Load and prepare data
# --------------------------------------------------

def load_data():
    path = Path("data/processed/measurements.parquet")

    if not path.exists():
        st.error("No processed data found. Run extract.py first.")
        st.stop()

    data = pd.read_parquet(path)

    required_columns = {
        "site_code",
        "pollutant",
        "timestamp",
        "value",
    }

    if not required_columns.issubset(data.columns):
        st.error("The processed dataset is missing required columns.")
        st.stop()

    data = data[
        ["site_code", "pollutant", "timestamp", "value"]
    ].copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="coerce"
    )

    if data["timestamp"].isna().any():
        st.error("Invalid or missing timestamps found. Run validate.py.")
        st.stop()

    if not pd.api.types.is_numeric_dtype(data["value"]):
        st.error("Measurement values must be numeric. Run validate.py.")
        st.stop()

    data = data[
        (data["timestamp"] >= STUDY_START)
        & (data["timestamp"] < STUDY_END)
    ].copy()

    keys = ["site_code", "pollutant", "timestamp"]

    if data.duplicated(subset=keys).any():
        st.error("Duplicate measurement keys found. Run validate.py.")
        st.stop()

    expected_hours = pd.date_range(
        start=STUDY_START,
        end=STUDY_END,
        freq="h",
        inclusive="left"
    )

    expected_index = pd.MultiIndex.from_tuples(
        [
            (site_code, pollutant, timestamp)
            for site_code, pollutant in CONFIGURED_STREAMS
            for timestamp in expected_hours
        ],
        names=keys
    )

    # Do not silently discard unexpected streams or off-hour timestamps.
    observed_index = pd.MultiIndex.from_frame(data[keys])

    if not observed_index.isin(expected_index).all():
        st.error(
            "Unexpected station-pollutant combinations or non-hourly "
            "timestamps found in the study period. Check the dataset."
        )
        st.stop()

    # Track records that were entirely absent from the stored dataset.
    data["record_present"] = True

    data = (
        data.set_index(keys)
        .reindex(expected_index)
        .reset_index()
    )

    data["record_present"] = data["record_present"].eq(True)

    data["site_name"] = data["site_code"].map(
        lambda code: STATION_METADATA[code][0]
    )

    data["site_type"] = data["site_code"].map(
        lambda code: STATION_METADATA[code][1]
    )

    return data


# Read on every Streamlit rerun so file updates are not hidden by a cache.
df = load_data()


# --------------------------------------------------
# Title and introduction
# --------------------------------------------------

st.title("London Air Quality: Roadside vs Urban Background")

st.caption(
    "Comparing NO₂ concentrations at selected monitoring stations, "
    "with data completeness shown alongside the findings. "
    "PM2.5 is available for secondary exploration of background stations."
)

st.caption(
    "Study window: 1 May 2026 00:00 UTC to 22 May 2026 00:00 UTC "
    "(end exclusive). Hourly profiles and daily trends use London local time."
)


# --------------------------------------------------
# Filters
# --------------------------------------------------

st.sidebar.header("Filters")

selected_pollutant = st.sidebar.selectbox(
    "Pollutant",
    sorted(df["pollutant"].unique()),
    format_func=lambda code: POLLUTANT_LABELS.get(code, code)
)

pollutant_label = POLLUTANT_LABELS.get(
    selected_pollutant,
    selected_pollutant
)

available_stations = sorted(
    df.loc[
        df["pollutant"] == selected_pollutant,
        "site_code"
    ].unique()
)

selected_stations = st.sidebar.multiselect(
    "Monitoring stations",
    available_stations,
    default=available_stations,
    format_func=lambda code: (
        f"{code} · {STATION_METADATA[code][0]}"
    )
)

if st.sidebar.button("Refresh data"):
    st.rerun()

if not selected_stations:
    st.warning("Select at least one monitoring station.")
    st.stop()

filtered = df[
    (df["pollutant"] == selected_pollutant)
    & (df["site_code"].isin(selected_stations))
].copy()


# --------------------------------------------------
# Overview
# --------------------------------------------------

st.header("Overview")

expected_records = len(filtered)
valid_records = int(filtered["value"].notna().sum())
completeness = valid_records / expected_records * 100

col1, col2, col3, col4 = st.columns(4)

col1.metric("Expected hourly readings", f"{expected_records:,}")
col2.metric("Valid readings", f"{valid_records:,}")
col3.metric("Stations", len(selected_stations))
col4.metric("Completeness", f"{completeness:.2f}%")

st.caption(
    "Completeness is valid readings divided by expected hourly readings. "
    "Both null readings and entirely absent records count as missing. "
    "Missing values are excluded from concentration averages, "
    "not treated as zero."
)

if selected_pollutant == "PM25":
    st.info(
        "PM2.5 is included only for BL0 and KC1 in this project. "
        "These are urban background stations, so this selection does "
        "not support a roadside versus background comparison."
    )


# --------------------------------------------------
# Fixed matched-hour comparison
# --------------------------------------------------

if selected_pollutant == "NO2":
    st.header("Roadside vs urban background")

    st.caption(
        "Fixed comparison: HG1 (roadside) vs KC1 (urban background). "
        "This comparison uses all matched NO₂ hours in the study period "
        "and is independent of the station filter."
    )

    paired = df[
        (df["pollutant"] == "NO2")
        & (df["site_code"].isin(["HG1", "KC1"]))
    ].pivot(
        index="timestamp",
        columns="site_code",
        values="value"
    )

    paired = (
        paired.reindex(columns=["HG1", "KC1"])
        .dropna(subset=["HG1", "KC1"])
        .copy()
    )

    if not paired.empty:
        paired["difference"] = paired["HG1"] - paired["KC1"]

        mean_difference = paired["difference"].mean()
        higher_pct = (paired["difference"] > 0).mean() * 100

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Matched hours",
            f"{len(paired):,}"
        )

        col2.metric(
            "Mean difference: HG1 − KC1",
            f"{mean_difference:+.2f} µg/m³"
        )

        col3.metric(
            "Hours HG1 was higher",
            f"{higher_pct:.2f}%"
        )

        st.caption(
            "Only hours with valid readings at both stations are used. "
            "Results describe these two stations during the study window "
            "and do not establish causation."
        )
    else:
        st.info(
            "No matched valid NO₂ readings are available "
            "for HG1 and KC1 in the study period."
        )


# --------------------------------------------------
# Station comparison
# --------------------------------------------------

st.header("Station comparison")

station_summary = filtered.groupby(
    ["site_code", "site_name", "site_type"],
    as_index=False
).agg(
    mean_value=("value", "mean"),
    median_value=("value", "median"),
    expected_hours=("value", "size"),
    valid_hours=("value", "count"),
    stored_records=("record_present", "sum")
)

station_summary["completeness_pct"] = (
    station_summary["valid_hours"]
    / station_summary["expected_hours"]
    * 100
).round(2)

station_summary["station_label"] = (
    station_summary["site_code"]
    + " · "
    + station_summary["site_name"]
)

fig_comparison = px.bar(
    station_summary,
    x="station_label",
    y="mean_value",
    color="site_type",
    labels={
        "station_label": "Monitoring station",
        "mean_value": f"Mean {pollutant_label} (µg/m³)",
        "site_type": "Station type"
    },
    title=f"Average {pollutant_label} concentration"
)

st.plotly_chart(fig_comparison, use_container_width=True)

st.dataframe(
    station_summary[
        [
            "site_code",
            "site_name",
            "site_type",
            "mean_value",
            "median_value",
            "completeness_pct"
        ]
    ].round(2),
    hide_index=True,
    use_container_width=True
)

st.caption(
    "Station averages use each station's available valid readings. "
    "They are not restricted to matched hours, so interpret them "
    "alongside completeness."
)


# --------------------------------------------------
# Hourly concentration patterns
# --------------------------------------------------

st.header("Hourly concentration patterns")

hourly = filtered.dropna(subset=["value"]).copy()

hourly["local_hour"] = (
    hourly["timestamp"]
    .dt.tz_convert("Europe/London")
    .dt.hour
)

hourly_summary = hourly.groupby(
    ["site_code", "local_hour"]
)["value"].mean()

# Keep missing hours visible as gaps.
hourly_index = pd.MultiIndex.from_product(
    [selected_stations, range(24)],
    names=["site_code", "local_hour"]
)

hourly_summary = (
    hourly_summary.reindex(hourly_index)
    .rename("value")
    .reset_index()
    .sort_values(["site_code", "local_hour"])
)

fig_hourly = px.line(
    hourly_summary,
    x="local_hour",
    y="value",
    color="site_code",
    markers=True,
    labels={
        "local_hour": "Hour of day (London local time)",
        "value": f"Mean {pollutant_label} (µg/m³)",
        "site_code": "Station"
    },
    title="Average concentration by hour of day"
)

fig_hourly.update_traces(connectgaps=False)

fig_hourly.update_xaxes(
    dtick=1,
    range=[0, 23]
)

st.plotly_chart(fig_hourly, use_container_width=True)

st.caption(
    "Each point averages available readings for that London local hour "
    "across the study window. These profiles use each station's available "
    "data and may be affected by differences in completeness."
)


# --------------------------------------------------
# Daily concentration trends
# --------------------------------------------------

st.header("Daily concentration trends")

daily = filtered.copy()

daily["date"] = (
    daily["timestamp"]
    .dt.tz_convert("Europe/London")
    .dt.tz_localize(None)
    .dt.normalize()
)

daily_summary = daily.groupby(
    ["site_code", "date"]
).agg(
    mean_value=("value", "mean"),
    valid_hours=("value", "count")
)

local_dates = pd.date_range(
    start="2026-05-01",
    end="2026-05-21",
    freq="D"
)

daily_index = pd.MultiIndex.from_product(
    [selected_stations, local_dates],
    names=["site_code", "date"]
)

daily_summary = daily_summary.reindex(daily_index)

daily_summary["valid_hours"] = (
    daily_summary["valid_hours"].fillna(0).astype(int)
)

# Retain each date, but hide averages with insufficient valid readings.
# Keeping the date with a missing mean makes Plotly display a gap.
daily_summary.loc[
    daily_summary["valid_hours"] < MIN_DAILY_HOURS,
    "mean_value"
] = float("nan")

daily_summary = (
    daily_summary.reset_index()
    .sort_values(["site_code", "date"])
)

fig_daily = px.line(
    daily_summary,
    x="date",
    y="mean_value",
    color="site_code",
    markers=True,
    hover_data={"valid_hours": True},
    labels={
        "date": "Date (London local time)",
        "mean_value": f"Daily mean {pollutant_label} (µg/m³)",
        "site_code": "Station",
        "valid_hours": "Valid hourly readings"
    },
    title="Daily average pollutant concentration"
)

fig_daily.update_traces(connectgaps=False)

fig_daily.update_xaxes(
    range=["2026-05-01", "2026-05-22"],
    tickformat="%d %b"
)

st.plotly_chart(fig_daily, use_container_width=True)

st.caption(
    f"Daily averages require at least {MIN_DAILY_HOURS} valid hourly "
    "readings. Dates below this threshold appear as gaps. "
    "This is a project-defined threshold, not an official LAQN standard. "
    "The UTC extraction window starts at 01:00 London local time on "
    "1 May, so that local day has only 23 expected readings in this dataset."
)


# --------------------------------------------------
# Data quality
# --------------------------------------------------

st.header("Data quality")

quality = station_summary[
    [
        "site_code",
        "site_type",
        "expected_hours",
        "stored_records",
        "valid_hours",
        "completeness_pct"
    ]
].copy()

quality["absent_records"] = (
    quality["expected_hours"] - quality["stored_records"]
)

quality["null_readings"] = (
    quality["stored_records"] - quality["valid_hours"]
)

quality["missing_hours"] = (
    quality["expected_hours"] - quality["valid_hours"]
)

fig_quality = px.bar(
    quality,
    x="site_code",
    y="completeness_pct",
    color="site_type",
    labels={
        "site_code": "Monitoring station",
        "completeness_pct": "Completeness (%)",
        "site_type": "Station type"
    },
    title="Data completeness by station",
    range_y=[0, 100]
)

st.plotly_chart(fig_quality, use_container_width=True)

st.dataframe(
    quality,
    hide_index=True,
    use_container_width=True
)

st.caption(
    "Each configured station-pollutant combination has 504 expected "
    "hourly readings in the UTC study window. Missing hours include "
    "stored null readings and records absent from the processed file. "
    "Expected rows added for display are not written back to Parquet."
)

st.info(
    "The pipeline supports historical backfills and incremental updates. "
    "This dashboard uses a fixed study window for consistent comparisons. "
    "Observed differences may reflect location, weather and other factors; "
    "they do not establish the cause of pollution differences."
)