import requests
import pandas as pd

stations = ["CR9", "GN4", "HG1"]
pollutants = ["NO2", "PM25"]

for site_code in stations:
    for pollutant in pollutants:
        url = (
            "https://api.erg.ic.ac.uk/AirQuality/Data/SiteSpecies/"
            f"SiteCode={site_code}/SpeciesCode={pollutant}/"
            "StartDate=01-May-2026/"
            "EndDate=04-May-2026/Json"
        )

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            raw = response.json().get("RawAQData", {})
            measurements = raw.get("Data", [])

            if isinstance(measurements, dict):
                measurements = [measurements]

            df = pd.DataFrame(measurements)

            if "@Value" in df.columns:
                valid = pd.to_numeric(
                    df["@Value"], errors="coerce"
                ).notna().sum()
            else:
                valid = 0

            print(
                f"{site_code} / {pollutant}: "
                f"{len(df)} rows, {valid} valid values"
            )

        except (requests.RequestException, ValueError) as error:
            print(f"{site_code} / {pollutant}: ERROR - {error}")