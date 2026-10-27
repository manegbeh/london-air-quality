
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="London Air Quality Explorer",
    page_icon="🌍",
    layout="wide"
)

STATION_METADATA = {
    "BL0": ("Camden - Bloomsbury", "Urban Background"),
    "KC1": ("North Kensington", "Urban Background"),
    "GN4": ("Greenwich - Fiveways A20", "Roadside"),
    "HG1": ("Haringey Town Hall", "Roadside"),
}


@st.cache_data
def load_data():
    path = Path("data/processed/measurements.parquet")

    if not path.exists():
        st.error("No processed data found. Run extract.py first.")
        st.stop()

    df = pd.read_parquet(path)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True
    )

    df["site_name"] = df["site_code"].map(
        lambda code: STATION_METADATA.get(
            code, (code, "Unknown")
        )[0]
    )

    df["site_type"] = df["site_code"].map(
        lambda code: STATION_METADATA.get(
            code, (code, "Unknown")
        )[1]
    )

    return df


df = load_data()

st.title("London Air Quality Explorer")
st.caption(
    "An incremental data engineering pipeline using "
    "London Air Quality Network monitoring data."
)

# Keep comparisons within the common May study period.
study_start = pd.Timestamp("2026-05-01", tz="UTC")
study_end = pd.Timestamp("2026-05-22", tz="UTC")

df = df[
    (df["timestamp"] >= study_start)
    & (df["timestamp"] < study_end)
].copy()

st.sidebar.header("Filters")

selected_pollutant = st.sidebar.selectbox(
    "Pollutant",
    sorted(df["pollutant"].unique())
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
    default=available_stations
)

filtered = df[
    (df["pollutant"] == selected_pollutant)
    & (df["site_code"].isin(selected_stations))
].copy()

if filtered.empty:
    st.warning("Select at least one monitoring station.")
    st.stop()


# --------------------------------------------------
# Overview
# --------------------------------------------------

st.header("Overview")

total_records = len(filtered)
valid_records = filtered["value"].notna().sum()
completeness = valid_records / total_records * 100

col1, col2, col3, col4 = st.columns(4)

col1.metric("Measurements", f"{total_records:,}")
col2.metric("Valid readings", f"{valid_records:,}")
col3.metric("Stations", filtered["site_code"].nunique())
col4.metric("Completeness", f"{completeness:.1f}%")

st.caption(
    "Missing values are excluded from concentration averages, "
    "not treated as zero."
)

# --------------------------------------------------
# Matched hourly comparison
# --------------------------------------------------

if selected_pollutant == "NO2":
    st.header("Roadside vs urban background")

    paired = df[
        (df["pollutant"] == "NO2")
        & (df["site_code"].isin(["HG1", "KC1"]))
    ].pivot_table(
        index="timestamp",
        columns="site_code",
        values="value"
    )

    paired = paired.dropna(subset=["HG1", "KC1"])

    if not paired.empty:
        paired["difference"] = paired["HG1"] - paired["KC1"]

        mean_difference = paired["difference"].mean()

        higher_pct = (
            (paired["difference"] > 0).mean() * 100
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Matched hours",
            f"{len(paired):,}"
        )

        col2.metric(
            "Average roadside increase",
            f"+{mean_difference:.2f} µg/m³"
        )

        col3.metric(
            "Hours roadside was higher",
            f"{higher_pct:.2f}%"
        )

        st.caption(
            "Comparison of HG1 (roadside) and KC1 "
            "(urban background) at identical timestamps. "
            "Results describe these two stations during "
            "1–21 May 2026 and do not establish causation."
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
    total_hours=("value", "size"),
    valid_hours=("value", "count")
)

station_summary["completeness_pct"] = (
    station_summary["valid_hours"]
    / station_summary["total_hours"]
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
        "mean_value": f"Mean {selected_pollutant} (µg/m³)",
        "site_type": "Station type"
    },
    title=f"Average {selected_pollutant} concentration"
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


# --------------------------------------------------
# Hourly pattern
# --------------------------------------------------

st.header("Hourly concentration patterns")

hourly = filtered.dropna(subset=["value"]).copy()

hourly["local_hour"] = (
    hourly["timestamp"]
    .dt.tz_convert("Europe/London")
    .dt.hour
)

hourly_summary = hourly.groupby(
    ["local_hour", "site_code"],
    as_index=False
)["value"].mean()

fig_hourly = px.line(
    hourly_summary,
    x="local_hour",
    y="value",
    color="site_code",
    markers=True,
    labels={
        "local_hour": "Hour of day (London local time)",
        "value": f"Mean {selected_pollutant} (µg/m³)",
        "site_code": "Station"
    },
    title="Average concentration by hour of day"
)

fig_hourly.update_xaxes(
    dtick=1,
    range=[0, 23]
)

st.plotly_chart(fig_hourly, use_container_width=True)

st.caption(
    "Hourly averages use available readings. "
    "Station comparisons may be affected by differences "
    "in data completeness."
)

# --------------------------------------------------
# Daily concentration trends
# --------------------------------------------------

st.header("Daily concentration trends")

daily = filtered.dropna(subset=["value"]).copy()

# Group by London calendar date rather than UTC date.
daily["date"] = (
    daily["timestamp"]
    .dt.tz_convert("Europe/London")
    .dt.date
)

daily_summary = daily.groupby(
    ["date", "site_code"],
    as_index=False
).agg(
    mean_value=("value", "mean"),
    valid_hours=("value", "count")
)

# Only show dates within our intended local study period.
daily_summary = daily_summary[
    (pd.to_datetime(daily_summary["date"]) >= pd.Timestamp("2026-05-01"))
    & (pd.to_datetime(daily_summary["date"]) <= pd.Timestamp("2026-05-21"))
]

# Require at least 18 valid hourly readings per day.
daily_summary = daily_summary[
    daily_summary["valid_hours"] >= 18
].copy()

fig_daily = px.line(
    daily_summary,
    x="date",
    y="mean_value",
    color="site_code",
    markers=True,
    labels={
        "date": "Date",
        "mean_value": f"Daily mean {selected_pollutant} (µg/m³)",
        "site_code": "Station"
    },
    title="Daily average pollutant concentration"
)

fig_daily.update_xaxes(
    range=["2026-05-01", "2026-05-22"],
    tickformat="%d %b"
)

st.plotly_chart(fig_daily, use_container_width=True)

st.caption(
    "Daily averages use London local time and require "
    "at least 18 valid hourly readings. "
    "Incomplete station-days are excluded."
)

# --------------------------------------------------
# Data quality
# --------------------------------------------------

st.header("Data quality")

quality = station_summary[
    [
        "site_code",
        "site_type",
        "total_hours",
        "valid_hours",
        "completeness_pct"
    ]
].copy()

quality["missing_hours"] = (
    quality["total_hours"] - quality["valid_hours"]
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

st.info(
    "This analysis covers 1–21 May 2026. "
    "The pipeline supports historical backfills and "
    "incremental updates, but the dashboard currently "
    "uses a fixed study period for consistent comparisons."
)
