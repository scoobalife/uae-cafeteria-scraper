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

if __name__ == "__main__":
    # Receives the cafeteria list directly from Claude via workflow input
    raw_input = sys.argv[1] if len(sys.argv) > 1 else "[]"
    restaurants = json.loads(raw_input)

    all_data = []
    for name in restaurants:
        print(f"Scraping {name}...")
        all_data.extend(get_menu(name))
        time.sleep(2)

    if all_data:
        pd.DataFrame(all_data).to_csv("talabat_cafeterias.csv", index=False, encoding="utf-8-sig")
