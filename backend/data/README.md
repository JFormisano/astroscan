# Catalog data

`stars.json` and `constellation_lines.json` are derived from the two sources below. Because both sources are CC BY-SA 4.0, these derived files are licensed under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/) as well.

## stars.json

Filtered from the **HYG star database, version 4.4**, by David Nash (astronexus).

- Source: <https://codeberg.org/astronexus/hyg>
- File: `data/hyg/CURRENT/hyg_v44.csv.gz`
- License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

Changes made here: stars fainter than visual magnitude 7 were removed, the Sun (HYG id 0) was removed, right ascension was converted from hours to degrees, and only `id`, `hip`, `proper`, `bayer_flamsteed`, `constellation`, `ra_deg`, `dec_deg`, and `mag` were kept. Empty name fields are JSON `null`.

## constellation_lines.json

Stick figures for the 88 IAU constellations, taken from the `constellations` array in Stellarium's **modern** sky culture.

- Source file: <https://github.com/Stellarium/stellarium/blob/daace2add6a1bf886e8ee1934f51e9c69f818d18/skycultures/modern/index.json>
- Authors: the Stellarium team
- License of that sky culture's text and data, as stated in [`description.md`](https://github.com/Stellarium/stellarium/blob/daace2add6a1bf886e8ee1934f51e9c69f818d18/skycultures/modern/description.md): [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- The constellation illustrations in the same directory are under the Free Art License and are not included here.

Changes made here: each Hipparcos polyline was turned into line segments of J2000 right ascension and declination, using positions from HYG v4.4. Asterisms in the same file were not copied. `name` is the IAU Latin name (for example Vela). `common_name` is Stellarium's English name when the file has one (for example Sails).

## Regenerating

The raw downloads are large and are not committed. Put them in `data/raw/` (gitignored). The plain Codeberg URL for the catalog is a Git LFS pointer; use the object URL.

```bash
cd backend
mkdir -p data/raw
curl -L -o data/raw/hyg_v44.csv.gz \
  "https://codeberg.org/astronexus/hyg.git/info/lfs/objects/00b349893b9a53106dd488d8371e8d2fa586043e500bb3cdb8bff3931682197d"
curl -L -o data/raw/stellarium_modern_index.json \
  "https://raw.githubusercontent.com/Stellarium/stellarium/daace2add6a1bf886e8ee1934f51e9c69f818d18/skycultures/modern/index.json"
.venv/bin/python scripts/build_catalog.py \
  --hyg data/raw/hyg_v44.csv.gz \
  --stellarium data/raw/stellarium_modern_index.json
.venv/bin/python -m pytest tests/test_catalog.py -q
```
