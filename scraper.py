
# scraper.py
# CarWale API-based scraper (OLX disabled)

import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def scrape_carwale_city(city_name: str, max_pages: int = 3):
    listings = []

    session = requests.Session()
    session.headers.update(HEADERS)

    start_urls = {
        "Mumbai": "https://www.carwale.com/used/cars-in-mumbai/",
        "Delhi NCR": "https://www.carwale.com/used/cars-in-delhi-ncr/",
        "Bangalore": "https://www.carwale.com/used/cars-in-bangalore/",
        "Pune": "https://www.carwale.com/used/cars-in-pune/",
    }

    r = session.get(start_urls[city_name], timeout=20)
    html = r.text

    import re
    m = re.search(r'"nextPageUrl":"([^"]+/api/stocks/[^"]+)"', html)

    if not m:
        print(f"Could not locate CarWale API for {city_name}")
        return []

    api = "https://www.carwale.com" + m.group(1).replace("\\u0026", "&").replace("\\/", "/")

    for _ in range(max_pages):
        try:
            resp = session.get(api, timeout=20)
            data = resp.json()

            stocks = data.get("stocks") or data.get("data", {}).get("stocks") or []

            for car in stocks:
                listings.append({
                    "source": "CarWale",
                    "brand": car.get("makeName"),
                    "model": car.get("modelName"),
                    "year": car.get("manufactureYear"),
                    "asking_price": car.get("price"),
                    "km_driven": car.get("kmsDriven"),
                    "fuel_type": car.get("fuelType"),
                })

            next_url = data.get("nextPageUrl")
            if not next_url:
                break

            api = "https://www.carwale.com" + next_url

        except Exception as e:
            print("Error:", e)
            break

    return listings


if __name__ == "__main__":
    cities = ["Mumbai", "Delhi NCR", "Bangalore", "Pune"]

    rows = []
    for city in cities:
        print("Scraping", city)
        rows.extend(scrape_carwale_city(city))

    df = pd.DataFrame(rows)

    print(f"Collected {len(df)} listings")

    if len(df):
        df.to_csv("carwale_listings.csv", index=False)
        print("Saved carwale_listings.csv")
