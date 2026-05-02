# Met Museum 3D Scan Downloader

Downloads all 3D scans from the [Metropolitan Museum of Art's online collection](https://www.metmuseum.org/art/collection/search?showOnly=has3d), converts them from GLB to OBJ, and saves per-object metadata sidecars using the [Met Collection API](https://metmuseum.github.io/).

## Prerequisites

- [Miniconda or Anaconda](https://docs.conda.io/en/latest/miniconda.html)
- [Blender](https://www.blender.org/download/) — must be on your `PATH` (i.e. running `blender` in a terminal should work)

### Installing Blender

| Platform | Recommended method |
|---|---|
| macOS | `brew install --cask blender`, or download from blender.org and add to PATH |
| Linux | `sudo snap install blender --classic`, or your distro's package manager |
| Windows | Download installer from blender.org; add the install folder to your system PATH |

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/met-scans.git
cd met-scans

# 2. Create and activate the conda environment
conda env create -f environment.yml
conda activate met-scans

# 3. Install the Playwright browser engine
playwright install chromium
```

## Usage

### Step 1 — Scrape object IDs

This produces `object_ids.txt`, a list of every Met object that has a 3D scan.

```bash
python met-scrape.py > object_ids.txt
```

An `object_ids.txt` with the IDs current at the time of this release is included in the repo; you can skip this step if you want to use it as-is.

### Step 2 — Download scans and metadata

```bash
python met-download.py --contact "your.email@example.com"
```

**Required argument:**

| Argument | Description |
|---|---|
| `--contact` | Your email address or name, included in the HTTP User-Agent sent to the Met API. Required so the museum can reach you if needed. |

**Optional argument:**

| Argument | Default | Description |
|---|---|---|
| `--purpose` | `academic` | Purpose string included in the User-Agent header. |

Downloads are saved to `met-dataset/<object_id>/`:

```
met-dataset/
  10912/
    10912.glb       ← raw 3D scan
    10912.obj       ← converted mesh
    10912.mtl       ← materials
    10912.txt       ← metadata from the Met Collection API
```

Progress and errors are logged to `download_log.txt`.

## Notes

- The script resumes automatically: already-downloaded GLB and OBJ files are skipped.
- Rate-limit delays are built in (`PAGE_DELAY = 1 s`, `DL_DELAY = 5 s`).
- GLB files can be large (tens to hundreds of MB each). The full dataset is many GB.
- Blender is invoked as a subprocess for the GLB → OBJ conversion; make sure the `blender` command resolves correctly before running.
