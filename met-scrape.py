# met_scrape.py
import json, re, sys
from playwright.sync_api import sync_playwright

BASE = "https://www.metmuseum.org/art/collection/search?showOnly=has3d&offset={}&perPage=40"

def extract_ids(html: str) -> set[int]:
    # Try the structured path first: __NEXT_DATA__ JSON blob
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.S)
    ids = set()
    if m:
        def walk(x):
            if isinstance(x, dict):
                v = x.get("objectID")
                if isinstance(v, int): ids.add(v)
                for vv in x.values(): walk(vv)
            elif isinstance(x, list):
                for vv in x: walk(vv)
        try:
            walk(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    # Fallback: anchor hrefs
    ids.update(int(x) for x in re.findall(r'/art/collection/search/(\d+)', html))
    return ids

def main():
    all_ids: set[int] = set()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        offset = 0
        while True:
            page.goto(BASE.format(offset), wait_until="networkidle", timeout=30_000)
            html = page.content()
            new = extract_ids(html) - all_ids
            print(f"offset={offset}: +{len(new)} new (total {len(all_ids)+len(new)})", file=sys.stderr)
            if not new:
                break
            all_ids |= new
            offset += 40
        browser.close()
    for i in sorted(all_ids):
        print(i)

if __name__ == "__main__":
    main()
