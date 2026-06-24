"""
India Used Car Depreciation Scraper
Targets: OLX.in and CarWale.com
Run locally — requires: pip install requests playwright beautifulsoup4 pandas lxml
For JS-heavy pages: playwright install chromium
"""

import time
import random
import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CarListing:
    source: str                  # 'olx' | 'carwale'
    listing_id: str
    brand: str
    model: str
    variant: Optional[str]
    year: int
    age_years: int               # current_year - year
    fuel_type: str               # Petrol / Diesel / CNG / Electric
    transmission: str            # Manual / Automatic
    km_driven: int
    city: str
    state: str
    asking_price: int            # INR
    ex_showroom_price: Optional[int]  # seeded from price table if available
    depreciation_pct: Optional[float] # (ex_showroom - asking) / ex_showroom * 100
    owners: int
    scraped_at: str

# ---------------------------------------------------------------------------
# Ex-showroom reference prices (2020 launch prices, INR)
# Expand this dict with data from CarWale/CarDekho spec pages
# ---------------------------------------------------------------------------

EX_SHOWROOM_REF = {
    ("Maruti",   "Alto K10"):   380000,
    ("Maruti",   "Swift"):      620000,
    ("Maruti",   "Dzire"):      680000,
    ("Maruti",   "Ertiga"):     875000,
    ("Maruti",   "Baleno"):     700000,
    ("Hyundai",  "i20"):        750000,
    ("Hyundai",  "Creta"):      1100000,
    ("Hyundai",  "Verna"):      950000,
    ("Honda",    "City"):       1100000,
    ("Honda",    "Amaze"):      750000,
    ("Toyota",   "Innova"):     1700000,
    ("Toyota",   "Fortuner"):   3200000,
    ("Tata",     "Nexon"):      850000,
    ("Tata",     "Nexon EV"):   1400000,
    ("Tata",     "Harrier"):    1500000,
    ("Mahindra", "Scorpio N"):  1350000,
    ("Mahindra", "XUV700"):     1400000,
    ("Kia",      "Seltos"):     1100000,
    ("Kia",      "Carens"):     1000000,
    ("MG",       "Hector"):     1400000,
    ("BMW",      "3 Series"):   4700000,
    ("BMW",      "5 Series"):   6500000,
    ("Mercedes", "C-Class"):    5600000,
    ("Mercedes", "E-Class"):    7800000,
}

CURRENT_YEAR = datetime.now().year

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def polite_sleep(lo=2.0, hi=4.5):
    """Random delay between requests — be respectful of servers."""
    time.sleep(random.uniform(lo, hi))

def clean_price(text: str) -> Optional[int]:
    """Parse '₹ 4,50,000' or '4.5 Lakh' → int INR."""
    if not text:
        return None
    text = text.replace(",", "").replace("₹", "").strip()
    lakh_match = re.search(r"([\d.]+)\s*[Ll]akh", text)
    if lakh_match:
        return int(float(lakh_match.group(1)) * 100000)
    crore_match = re.search(r"([\d.]+)\s*[Cc]r", text)
    if crore_match:
        return int(float(crore_match.group(1)) * 10000000)
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None

def compute_depreciation(brand, model, asking_price) -> Optional[float]:
    """Return depreciation % vs ex-showroom reference if available."""
    ref = EX_SHOWROOM_REF.get((brand, model))
    if ref and asking_price:
        return round((1 - asking_price / ref) * 100, 2)
    return None

# ---------------------------------------------------------------------------
# OLX scraper (Playwright — OLX is heavily JS-rendered)
# ---------------------------------------------------------------------------

OLX_CITIES = {
    "mumbai": "mumbai",
    "delhi": "delhi_ncr",
    "bangalore": "bangalore",
    "chennai": "chennai",
    "hyderabad": "hyderabad",
    "pune": "pune",
    "kolkata": "kolkata",
    "ahmedabad": "ahmedabad",
}

def scrape_olx_city(city_slug: str, max_pages: int = 5) -> list[CarListing]:
    """
    Scrapes OLX used car listings for a given city.
    Uses Playwright for JS rendering.
    """
    from playwright.sync_api import sync_playwright

    listings = []
    base_url = f"https://www.olx.in/cars_c84/{city_slug}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="en-IN",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        page = ctx.new_page()

        for pg in range(1, max_pages + 1):
            url = base_url if pg == 1 else f"{base_url}?page={pg}"
            log.info(f"OLX {city_slug} page {pg}: {url}")
            try:
                page.goto(url, timeout=30000)
                page.wait_for_selector("li[data-aut-id='itemBox']", timeout=10000)
            except Exception as e:
                log.warning(f"OLX page load failed: {e}")
                break

            soup = BeautifulSoup(page.content(), "lxml")
            cards = soup.select("li[data-aut-id='itemBox']")
            if not cards:
                log.info("No more OLX cards found, stopping.")
                break

            for card in cards:
                try:
                    title_el = card.select_one("span[data-aut-id='itemTitle']")
                    price_el = card.select_one("span[data-aut-id='itemPrice']")
                    detail_els = card.select("span[data-aut-id='item-detail']")

                    if not title_el or not price_el:
                        continue

                    raw_title = title_el.get_text(strip=True)
                    # Title usually: "2019 Maruti Swift VXI" or "Hyundai i20 2021"
                    parts = raw_title.split()
                    year = None
                    for part in parts:
                        if re.match(r"20\d{2}", part):
                            year = int(part)
                            break
                    if not year:
                        continue

                    # Extract brand/model heuristically
                    known_brands = list({b for b, _ in EX_SHOWROOM_REF})
                    brand, model = "Unknown", raw_title
                    for b in known_brands:
                        if b.lower() in raw_title.lower():
                            brand = b
                            # model = next word after brand
                            idx = raw_title.lower().find(b.lower())
                            after = raw_title[idx + len(b):].strip().split()
                            model = after[0] if after else b
                            break

                    price = clean_price(price_el.get_text(strip=True))
                    km_text = next((d.get_text(strip=True) for d in detail_els if "km" in d.get_text().lower()), "0 km")
                    km = int(re.sub(r"[^\d]", "", km_text) or 0)

                    listing = CarListing(
                        source="olx",
                        listing_id=card.get("data-aut-id", f"olx_{random.randint(100000,999999)}"),
                        brand=brand,
                        model=model,
                        variant=None,
                        year=year,
                        age_years=CURRENT_YEAR - year,
                        fuel_type="Unknown",
                        transmission="Unknown",
                        km_driven=km,
                        city=city_slug.replace("_", " ").title(),
                        state="",
                        asking_price=price or 0,
                        ex_showroom_price=EX_SHOWROOM_REF.get((brand, model)),
                        depreciation_pct=compute_depreciation(brand, model, price),
                        owners=1,
                        scraped_at=datetime.utcnow().isoformat(),
                    )
                    listings.append(listing)
                except Exception as e:
                    log.debug(f"Card parse error: {e}")
                    continue

            polite_sleep()

        browser.close()

    log.info(f"OLX {city_slug}: {len(listings)} listings collected")
    return listings


# ---------------------------------------------------------------------------
# CarWale scraper (requests + BS4 — partially server-rendered)
# ---------------------------------------------------------------------------

CARWALE_CITIES = {
    "Mumbai": 1,
    "Delhi NCR": 3,
    "Bangalore": 2,
    "Chennai": 4,
    "Hyderabad": 5,
    "Pune": 6,
    "Kolkata": 7,
    "Ahmedabad": 8,
}

def scrape_carwale_city(city_name: str, max_pages: int = 5) -> list[CarListing]:
    """
    Scrapes CarWale used car listings for a given city.
    CarWale uses a mix of SSR and JSON embedded in <script> tags.
    """
    import requests

    listings = []
    city_id = CARWALE_CITIES.get(city_name, 1)
    session = requests.Session()
    session.headers.update(HEADERS)

    for pg in range(1, max_pages + 1):
        url = (
            f"https://www.carwale.com/used/cars-in-{city_name.lower().replace(' ','-')}/"
            f"?page={pg}"
        )
        log.info(f"CarWale {city_name} page {pg}: {url}")

        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            log.warning(f"CarWale request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # CarWale embeds listing JSON in window.__INITIAL_STATE__
        script_tags = soup.find_all("script")
        json_data = None
        for sc in script_tags:
            if sc.string and "usedCarList" in (sc.string or ""):
                try:
                    raw = sc.string
                    start = raw.index("{")
                    json_data = json.loads(raw[start:])
                    break
                except Exception:
                    continue

        if json_data:
            # Parse from JSON (most reliable)
            cars = (
                json_data.get("usedCarList", {}).get("cars", [])
                or json_data.get("listingData", {}).get("listing", [])
            )
            for car in cars:
                try:
                    brand = car.get("make", "Unknown")
                    model = car.get("model", "Unknown")
                    year  = int(car.get("year", CURRENT_YEAR))
                    price = int(car.get("price", 0))
                    km    = int(car.get("kilometerDriven", 0))
                    fuel  = car.get("fuel", "Unknown")
                    trans = car.get("transmission", "Unknown")
                    owners = int(car.get("owners", 1))

                    listings.append(CarListing(
                        source="carwale",
                        listing_id=str(car.get("id", random.randint(100000, 999999))),
                        brand=brand, model=model, variant=car.get("version"),
                        year=year, age_years=CURRENT_YEAR - year,
                        fuel_type=fuel, transmission=trans,
                        km_driven=km, city=city_name, state="",
                        asking_price=price,
                        ex_showroom_price=EX_SHOWROOM_REF.get((brand, model)),
                        depreciation_pct=compute_depreciation(brand, model, price),
                        owners=owners,
                        scraped_at=datetime.utcnow().isoformat(),
                    ))
                except Exception as e:
                    log.debug(f"CarWale JSON car parse error: {e}")
        else:
            # Fallback: parse HTML cards
            cards = soup.select(".used-car-card, .listing-card, [data-listing-id]")
            for card in cards:
                try:
                    title = card.select_one("h3, .car-name, [class*='title']")
                    price_el = card.select_one("[class*='price'], .price")
                    if not title or not price_el:
                        continue
                    raw_title = title.get_text(strip=True)
                    price = clean_price(price_el.get_text(strip=True))

                    year_match = re.search(r"20\d{2}", raw_title)
                    year = int(year_match.group()) if year_match else CURRENT_YEAR - 3

                    brand, model = "Unknown", raw_title
                    for b in {b for b, _ in EX_SHOWROOM_REF}:
                        if b.lower() in raw_title.lower():
                            brand = b
                            after = raw_title.lower().split(b.lower())[-1].strip().split()
                            model = after[0].title() if after else b
                            break

                    listings.append(CarListing(
                        source="carwale",
                        listing_id=card.get("data-listing-id", str(random.randint(100000,999999))),
                        brand=brand, model=model, variant=None,
                        year=year, age_years=CURRENT_YEAR - year,
                        fuel_type="Unknown", transmission="Unknown",
                        km_driven=0, city=city_name, state="",
                        asking_price=price or 0,
                        ex_showroom_price=EX_SHOWROOM_REF.get((brand, model)),
                        depreciation_pct=compute_depreciation(brand, model, price),
                        owners=1,
                        scraped_at=datetime.utcnow().isoformat(),
                    ))
                except Exception as e:
                    log.debug(f"CarWale HTML card error: {e}")

        polite_sleep()

    log.info(f"CarWale {city_name}: {len(listings)} listings collected")
    return listings


# ---------------------------------------------------------------------------
# Depreciation model computation
# ---------------------------------------------------------------------------

def build_depreciation_model(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates raw listings into a depreciation model.
    Groups by brand, model, city, age_years.
    Returns mean/median depreciation % and value-retained %.
    """
    df = df[df["asking_price"] > 50000].copy()
    df = df[df["age_years"].between(0, 15)].copy()
    df = df[df["depreciation_pct"].notna()].copy()

    model = (
        df.groupby(["brand", "model", "city", "age_years", "fuel_type"])
        .agg(
            listings_count=("listing_id", "count"),
            mean_asking_price=("asking_price", "mean"),
            median_asking_price=("asking_price", "median"),
            mean_depreciation_pct=("depreciation_pct", "mean"),
            median_depreciation_pct=("depreciation_pct", "median"),
            mean_km_driven=("km_driven", "mean"),
            ex_showroom_price=("ex_showroom_price", "first"),
        )
        .reset_index()
    )

    model["value_retained_pct"] = (100 - model["mean_depreciation_pct"]).round(2)
    model["mean_depreciation_pct"] = model["mean_depreciation_pct"].round(2)
    model["mean_asking_price"] = model["mean_asking_price"].round(0).astype(int)
    model = model[model["listings_count"] >= 2]  # min 2 listings for reliability
    model = model.sort_values(["brand", "model", "city", "age_years"])
    return model


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_full_scrape(
    cities: list[str] = None,
    olx_pages: int = 3,
    carwale_pages: int = 3,
    out_dir: str = "data",
):
    if cities is None:
        cities = list(CARWALE_CITIES.keys())

    Path(out_dir).mkdir(exist_ok=True)
    all_listings = []

    # --- OLX ---
    olx_city_map = {v.replace("_"," ").title(): k for k, v in OLX_CITIES.items()}
    for city in cities:
        slug = OLX_CITIES.get(city.lower(), city.lower().replace(" ","_"))
        try:
            data = scrape_olx_city(slug, max_pages=olx_pages)
            all_listings.extend(data)
        except Exception as e:
            log.error(f"OLX {city} failed: {e}")

    # --- CarWale ---
    for city in cities:
        if city in CARWALE_CITIES:
            try:
                data = scrape_carwale_city(city, max_pages=carwale_pages)
                all_listings.extend(data)
            except Exception as e:
                log.error(f"CarWale {city} failed: {e}")

    if not all_listings:
        log.warning("No listings collected.")
        return

    # Save raw
    raw_df = pd.DataFrame([asdict(l) for l in all_listings])
    raw_path = f"{out_dir}/raw_listings_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    raw_df.to_csv(raw_path, index=False)
    log.info(f"Raw listings saved → {raw_path} ({len(raw_df)} rows)")

    # Build depreciation model
    model_df = build_depreciation_model(raw_df)
    model_path = f"{out_dir}/depreciation_model_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    model_df.to_csv(model_path, index=False)
    log.info(f"Depreciation model saved → {model_path} ({len(model_df)} rows)")

    print("\n=== TOP 20 DEPRECIATION MODEL ROWS ===")
    print(model_df.head(20).to_string(index=False))
    return raw_df, model_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="India Used Car Depreciation Scraper")
    parser.add_argument("--cities", nargs="+", default=["Mumbai", "Delhi NCR", "Bangalore", "Pune"],
                        help="Cities to scrape")
    parser.add_argument("--olx-pages", type=int, default=3)
    parser.add_argument("--carwale-pages", type=int, default=3)
    parser.add_argument("--out-dir", default="data")
    args = parser.parse_args()

    run_full_scrape(
        cities=args.cities,
        olx_pages=args.olx_pages,
        carwale_pages=args.carwale_pages,
        out_dir=args.out_dir,
    )
