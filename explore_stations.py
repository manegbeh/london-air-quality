import requests
import pandas as pd

url = (
    "https://api.erg.ic.ac.uk/AirQuality/"
    "Information/MonitoringSites/GroupName=London/Json"
)

response = requests.get(url, timeout=30)
response.raise_for_status()

data = response.json()

stations = pd.DataFrame(data["Sites"]["Site"])

stations = stations.rename(columns={
    "@SiteCode": "site_code",
    "@SiteName": "site_name",
    "@SiteType": "site_type",
    "@DateClosed": "date_closed"
})

active_stations = stations[
    stations["date_closed"].fillna("").eq("")
].copy()

print("Total stations:", len(stations))
print("Active stations:", len(active_stations))

print("\nActive station types:")
print(active_stations["site_type"].value_counts())

print("\nRoadside and urban background stations:")
selected = active_stations[
    active_stations["site_type"].isin([
        "Roadside",
        "Urban Background"
    ])
]

print(
    selected[
        ["site_code", "site_name", "site_type"]
    ].head(30).to_string(index=False)
)