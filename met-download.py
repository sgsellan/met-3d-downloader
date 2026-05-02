# met_download.py
"""Download Met 3D scans, convert to OBJ, save metadata sidecars.

Usage:
    pip install playwright trimesh pillow networkx
    playwright install chromium
    python met_download.py
"""
import json, re, sys, time, urllib.request, urllib.error, pathlib, datetime
from playwright.sync_api import sync_playwright
import trimesh

IDS_FILE  = pathlib.Path("object_ids.txt")
LOG_FILE  = pathlib.Path("download_log.txt")
GLB_DIR   = pathlib.Path("glb")
# OBJ_DIR   = pathlib.Path("obj") 
DATASET_DIR = pathlib.Path("met-dataset")
PAGE_DELAY = 1.0
DL_DELAY   = 5.0

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.metmuseum.org/",
    "Accept": "*/*",
}

def log(msg: str) -> None:
    LOG_FILE.open("a").write(msg + "\n")

# ---------- metadata ------------------------------------------------------

import urllib.error

API_HEADERS = {
    "User-Agent": "met-scans-downloader/1.0 (academic; contact: silvia)",
    "Accept": "application/json",
}

import requests

_API_SESSION = requests.Session()
_API_SESSION.headers.update({
    "User-Agent": "met-scans/1.0",
    "Accept": "application/json",
})

def fetch_metadata(object_id: str, retries: int = 3) -> dict | None:
    url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
    for attempt in range(retries):
        try:
            r = _API_SESSION.get(url, timeout=30)
            if r.status_code in (404, 410):
                return None                           # object not in API
            if r.status_code == 429:                  # rate limited
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"    metadata fetch failed: {e}")
            return None
    return None

def write_metadata(meta: dict, out_path: pathlib.Path) -> None:
    """Pretty-print every non-empty field as `Key: value`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for k, v in meta.items():
            if v in (None, "", [], {}):
                continue
            if isinstance(v, list):
                # tags is a list of dicts; flatten to term names if so
                if v and isinstance(v[0], dict) and "term" in v[0]:
                    v = ", ".join(t["term"] for t in v)
                else:
                    v = ", ".join(str(x) for x in v)
            elif isinstance(v, dict):
                v = json.dumps(v, ensure_ascii=False)
            f.write(f"{k}: {v}\n")

# ---------- GLB → OBJ -----------------------------------------------------
import subprocess, shutil

BLENDER = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"

def convert_glb_to_obj(glb_path: pathlib.Path, obj_path: pathlib.Path) -> bool:
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [BLENDER, "-b", "--factory-startup",
             "-P", "glb-to-obj-blender.py",
             "--", str(glb_path), str(obj_path)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0 or not obj_path.exists():
            print(f"    Blender conversion failed (rc={result.returncode})")
            print(f"    stderr tail: {result.stderr[-400:]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"    Blender timed out on {glb_path.name}")
        return False
    except Exception as e:
        print(f"    Blender invocation failed: {e}")
        return False

# ---------- vntana asset extraction (unchanged logic) ---------------------

def find_vntana_assets(obj):
    if isinstance(obj, dict):
        if "vntanaAssets" in obj and isinstance(obj["vntanaAssets"], list):
            return obj["vntanaAssets"]
        for v in obj.values():
            r = find_vntana_assets(v)
            if r is not None: return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_vntana_assets(v)
            if r is not None: return r
    return None

def extract_assets(html: str):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.S)
    if m:
        try:
            assets = find_vntana_assets(json.loads(m.group(1)))
            if assets: return assets
        except json.JSONDecodeError:
            pass
    idx = html.find("vntanaAssets")
    if idx < 0: return []
    chunk = html[idx:idx+60000].replace('\\\\', '\\').replace('\\"', '"')
    start = chunk.find('[')
    if start < 0: return []
    depth = 0; in_str = False; esc = False; end = -1
    for i, c in enumerate(chunk[start:]):
        if esc: esc = False; continue
        if c == '\\': esc = True; continue
        if c == '"': in_str = not in_str
        if not in_str:
            if c == '[': depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0: end = start + i + 1; break
    if end < 0: return []
    try:
        return json.loads(chunk[start:end])
    except json.JSONDecodeError:
        return []

def glb_jobs(object_id: str, assets: list):
    n = 0
    for a in assets:
        uuid = a.get("uuid", "")
        client = a.get("clientSlug", "masters")
        for m in a.get("asset", {}).get("models", []):
            if m["conversionFormat"] != "GLB":
                continue
            n += 1
            suffix = "" if n == 1 else f"_{n}"
            blob = m["modelBlobId"]
            url = (f"https://api.vntana.com/assets/products/{uuid}"
                   f"/organizations/The-Metropolitan-Museum-of-Art"
                   f"/clients/{client}/{blob}")
            glb_path = DATASET_DIR / object_id / f"{object_id}{suffix}.glb"
            size_mb = m.get("modelSize", 0) / 1024 / 1024
            polys = m.get("optimizationThreeDComponents", {}).get("poly", "?")
            yield url, glb_path, size_mb, polys, suffix

def download(url: str, out_path: pathlib.Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(out_path, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
        return True
    except Exception as e:
        if out_path.exists(): out_path.unlink()
        print(f"    download failed: {e}")
        return False

# ---------- main ----------------------------------------------------------

def main():
    if not IDS_FILE.exists():
        sys.exit(f"missing {IDS_FILE}")
    ids = [x.strip() for x in IDS_FILE.read_text().splitlines() if x.strip()]
    total = len(ids)
    print(f"Downloading {total} Met 3D objects (GLB → OBJ + metadata)")
    log(f"{datetime.datetime.now()}: batch start")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=HEADERS["User-Agent"])
        page = ctx.new_page()

        for i, oid in enumerate(ids, 1):
            obj_dir = DATASET_DIR / oid
            txt_path = obj_dir / f"{oid}.txt"

            # --- metadata (cheap; do first so even non-3D pages get a sidecar)
            if not txt_path.exists():
                meta = fetch_metadata(oid)
                if meta:
                    write_metadata(meta, txt_path)
                    log(f"META {oid}")

            # --- 3D page scrape
            try:
                page.goto(f"https://www.metmuseum.org/art/collection/search/{oid}",
                          wait_until="networkidle", timeout=30_000)
                html = page.content()
            except Exception as e:
                print(f"  [{i}/{total}] {oid}: page fetch failed ({e})")
                log(f"FAIL_PAGE {oid}")
                continue

            assets = extract_assets(html)
            if not assets:
                print(f"  [{i}/{total}] {oid}: no 3D data")
                log(f"NO_3D {oid}")
                time.sleep(PAGE_DELAY)
                continue

            for url, glb_path, size_mb, polys, suffix in glb_jobs(oid, assets):
                obj_path = obj_dir / f"{oid}{suffix}.obj"

                if obj_path.exists():
                    print(f"  [{i}/{total}] {obj_path}: exists, skip")
                    log(f"SKIP {oid} {obj_path}")
                    continue

                # download GLB if missing
                if not glb_path.exists():
                    print(f"  [{i}/{total}] {glb_path} ({size_mb:.1f} MB, {polys} polys)")
                    if not download(url, glb_path):
                        log(f"FAIL_DL {oid} {glb_path}")
                        time.sleep(DL_DELAY)
                        continue
                    log(f"OK_DL {oid} {glb_path}")
                    time.sleep(DL_DELAY)

                # convert
                print(f"            → {obj_path}")
                if convert_glb_to_obj(glb_path, obj_path):
                    log(f"OK_CONV {oid} {obj_path}")
                else:
                    log(f"FAIL_CONV {oid} {obj_path}")

            time.sleep(PAGE_DELAY)
        browser.close()

    log(f"{datetime.datetime.now()}: batch finished")
    print("Done. See download_log.txt.")

if __name__ == "__main__":
    main()