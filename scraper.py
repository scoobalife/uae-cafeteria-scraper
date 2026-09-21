import json
import re
import sys
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# Column headers that may hold restaurant names (matched case-insensitively).
# restaurants.xlsx uses 'Name' on the Directory sheet and 'Brand' on Chain Branches.
NAME_COLUMNS = ['name', 'restaurant', 'restaurant name', 'cafeteria', 'brand']


def get_menu(restaurant_name):
    query = f'"{restaurant_name}" site:talabat.com/uae/restaurant'
    url = None
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=3):
            if "/restaurant/" in r.get("href", ""):
                url = r["href"]
                break
    if not url:
        return []

    resp = requests.get(url, headers=HEADERS, timeout=12)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    
    # 1. Parse __NEXT_DATA__
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag and script_tag.string:
        try:
            data = json.loads(script_tag.string)
            sections = (
                data.get("props", {})
                .get("pageProps", {})
                .get("initialMenuState", {})
                .get("menuData", {})
                .get("sections", [])
            )
            for sec in sections:
                for itm in sec.get("items", []):
                    items.append({
                        "restaurant": restaurant_name,
                        "category": sec.get("name"),
                        "item": itm.get("name"),
                        "price": itm.get("price"),
                        "url": url
                    })
            if items:
                return items
        except Exception:
            pass

    # 2. HTML Fallback
    for card in soup.select('[data-testid="menu-item"], div.menu-item'):
        t = card.find(["h4", "h5", "strong"])
        p = card.find(string=re.compile(r"AED|\d+\.\d+"))
        if t and p:
            items.append({
                "restaurant": restaurant_name,
                "category": "Menu",
                "item": t.get_text(strip=True),
                "price": p.strip(),
                "url": url
            })
    return items


def load_restaurants(path='restaurants.xlsx'):
    # Read all sheets into a dictionary of DataFrames
    sheets_dict = pd.read_excel(path, sheet_name=None)
    all_restaurants = []

    for sheet_name, df in sheets_dict.items():
        # Find the column containing restaurant names (case-insensitive)
        lookup = {str(c).strip().lower(): c for c in df.columns}
        col = next((lookup[k] for k in NAME_COLUMNS if k in lookup), None)
        if col is None:
            # e.g. the Summary sheet - skip rather than reading column 0
            print(f'Skipping sheet {sheet_name!r}: no restaurant-name column found.')
            continue
        names = df[col].dropna().astype(str).tolist()
        all_restaurants.extend(names)

    # Deduplicate and strip whitespace
    restaurants = sorted(list(set(r.strip() for r in all_restaurants if r.strip())))
    print(f'Loaded {len(restaurants)} unique restaurants across {len(sheets_dict)} sheets.')
    return restaurants


if __name__ == "__main__":
    restaurants = load_restaurants('restaurants.xlsx')

    all_data = []
    failed = []
    for i, name in enumerate(restaurants, 1):
        print(f"[{i}/{len(restaurants)}] Scraping {name}...")
        try:
            all_data.extend(get_menu(name))
        except Exception as e:
            # A rate limit or timeout on one restaurant should not lose the whole run
            print(f"  ! Failed: {type(e).__name__}: {e}")
            failed.append(name)
            time.sleep(10)
        time.sleep(2)

    print(f"Done. {len(all_data)} menu items collected; {len(failed)} restaurants failed.")

    if all_data:
        pd.DataFrame(all_data).to_csv("talabat_cafeterias.csv", index=False, encoding="utf-8-sig")
