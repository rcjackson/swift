# Swift retraining on observations

Working notes / progress log.

**Current direction (2026-09-22): observations gridded onto Swift's 1.40625 deg
grid, state variables only.** The gridding approach was developed against
**NNJA** (`gs://gcp-nnja-ai`) -- see [NNJA](#nnja-the-gridding-approach-developed-here) -- but the
*source* for training is now **CUON + CDS surface**, for the reason in
["Radiances have nowhere to go"](#radiances-have-nowhere-to-go-and-why-that-picks-the-source). Everything from ["The dataset"](#the-dataset) through ["2010 pilot:
COMPLETE"](#2010-pilot-complete) describes the **AIFS-DOP path**. Note that its
**two conventional recipes are back on the critical path** -- they are what
produces the 69 variables. Its eight radiance recipes are not, since radiances
are out of scope.

What the NNJA detour was worth: it established the gridded encoding, measured
that gridding is ~22x cheaper than storing observations, produced a validated
builder, and -- by forcing the question of where a brightness temperature would
actually enter the model -- established that radiances cannot be used at all
without new architecture. That is why the source came back to CDS.

**Decision (2026-09-22): train on the 69 state variables only, no radiances.**
Swift uses the same 69 variables as *both* input and target, and has no slot for
an observation of the state. That makes radiances unusable without new
architecture, and it makes **CUON + CDS surface the better source for the 69**
(1979+, real 600 hPa, native `q`) -- see
["Radiances have nowhere to go"](#radiances-have-nowhere-to-go-and-why-that-picks-the-source).
The NNJA gridding work stands: the builder, the grid convention, the `__cnt`
planes and the 2010 pilot all carry over to the conventional sources unchanged.

## Layout

| Path | What |
| --- | --- |
| `/lus/flare/projects/Swift-Reanalysis/work/nnja` | **current path**: NNJA gridding (`nnja_grid_pilot.py`, `README.md`) |
| `/lus/flare/projects/Swift-Reanalysis/work/nnja/grids/<ds>/YYYYMMDD_HH.h5` | gridded output, one file per 6-hour analysis window |
| `/lus/flare/projects/Swift-Reanalysis/work/recipes/observations` | *(AIFS-DOP)* the 10 build recipes + `combine.yaml` + `README.md` |
| `/lus/flare/projects/Swift-Reanalysis/work/synthetic` | synthetic ODB test fixtures (generated, disposable) |
| `/lus/flare/projects/Swift-Reanalysis/work/smoke` | smoke-test recipes + built zarrs (disposable) |
| `/lus/flare/projects/Swift-Reanalysis/work/make_synthetic_odb.py` | generates the fixtures |
| `/lus/flare/projects/Swift-Reanalysis/work/eumetsat_search.py` | search/download the EUMETSAT FDRs (HIRS, SSM/T-2) |
| `/lus/flare/projects/Swift-Reanalysis/work/fetch_cds_obs.py` | download CDS marine / land surface obs |
| `/lus/flare/projects/Swift-Reanalysis/work/cds_obs_to_wide.py` | pivot CDS long-format obs (surface + upper-air) to wide CSV |
| `/lus/flare/projects/Swift-Reanalysis/work/fetch_gridsat.py` | download GridSat-B1 from NOAA NCEI |
| `/lus/flare/projects/Swift-Reanalysis/work/amsua_to_wide.py` | flatten NOAA AMSU-A swath granules to wide CSV |
| `/lus/flare/projects/Swift-Reanalysis/work/fetch_noaa_mw.py` | download AMSU-B / MHS / MSU from AWS Open Data |
| `/lus/flare/projects/Swift-Reanalysis/work/mw_swath_to_wide.py` | flatten AMSU-A/B, MHS, MSU swaths (supersedes `amsua_to_wide.py`) |
| `/lus/flare/projects/Swift-Reanalysis/work/wide/` | wide-form CSVs the recipes actually read |
| `/lus/flare/projects/Swift-Reanalysis/anemoi-datasets` | anemoi-datasets checkout (v0.5.43) |
| `/lus/flare/projects/Swift-Reanalysis/swift` | this repo |
| `/lus/flare/projects/Swift-Reanalysis/miniforge3/envs/swift_env` | active conda env |

`/lus/flare/projects/Swift-Reanalysis` and `/flare/Swift-Reanalysis` are the same
filesystem via two mounts. ~5 TB free.

## The dataset

Ten recipes, one per instrument/category, each producing one **tabular** zarr.
They are combined at *training* time by `combine.yaml` (which is an
`open_dataset` config, not a build recipe — do not pass it to
`anemoi-datasets create`).

| Recipe | Instrument(s) | Period | Pivots to |
| --- | --- | --- | --- |
| `hirs-…` | HIRS | 1980–2021 | 19 channels |
| `msu-…` | MSU | 1980–2005 | 4 channels |
| `ssmt2-…` | SSM/T-2 | 1994–2005 | 5 channels |
| `amsua-…` | AMSU-A | 1998–2021 | 15 channels |
| `amsub-…` | AMSU-B | 1998–2014 | 5 channels |
| `mhs-…` | MHS | 2005–2021 | 5 channels |
| `atms-…` | ATMS | 2012–2021 | 22 channels |
| `gridsat-…` | GridSat | 1980–2021 | 3 bands |
| `surface-synop-ships-buoys` | SYNOP/buoy/ship | 1980–2021 | 2t, 2d, msl, 10u, 10v, sst |
| `upper-air-radiosonde-aircraft-amv` | radiosonde/aircraft/AMV | 1980–2021 | t, u, v, z, q per level |

All periods and citations were cross-checked against Table 1 and match exactly.

## Real data sources (replacing the ODB placeholders)

4 of the 10 datasets now build from **real, openly accessible data** — no ODB
archive and no ECMWF account needed. Credentials in `~/.cdsapirc` (CDS API).

| Dataset | Source | Status |
|---|---|---|
| surface (marine) | CDS `insitu-observations-surface-marine` (ICOADS R3.0 + C-RAID) | **built from real data** |
| surface (land) | CDS `insitu-observations-surface-land` (SYNOP) | **built from real data** |
| upper-air | CDS `insitu-comprehensive-upper-air-observation-network` (CUON) | **built from real data** |
| GridSat | NOAA NCEI GridSat-B1 CDR | **built from real data** |
| AMSU-A (window) | NOAA NCEI CICS AMSU-A FCDR (L1C swath) | **built**, 4 window channels |
| AMSU-A (sounding) | NOAA NESDIS gridded AMSU-A FCDR (L3 daily) | **built**, 11 channels 4–14 |
| AMSU-B | AWS `noaa-cdr-microwave-humidity-sounder-brit-temp-pds` | **built from real data**, all 5 channels |
| MHS | same bucket (split by filename) | **built from real data**, all 5 channels |
| MSU | AWS `noaa-cdr-msu-brit-temp-pds` | **built from real data**, all 4 channels |
| HIRS | EUMETSAT `EO:EUM:DAT:0961` | **built from real data**, all 20 channels |
| SSM/T-2 | EUMETSAT `EO:EUM:DAT:0343` | **built from real data**, all 5 channels |
| ATMS | EUMETSAT `EO:EUM:DAT:0345` | **built from real data**, all 22 channels |

### The shape problem, and how it is solved

The CDS in-situ products are **long format** — one row per observation, with the
quantity in an `observed_variable` column. anemoi's `odb:` source pivots this
itself via `pivot_columns`/`pivot_values`, but the `csv:` source **has no pivot
support and no per-date path patterns** (verified by reading
`create/sources/csv.py`), and there is no pivot filter in `anemoi.transform`.

So the flow is: download → pivot to wide CSV locally → `csv:` source →
`layout: tabular`. `cds_obs_to_wide.py` does the reshape.

Conversions it performs, all verified against physics:

- **Wind.** CDS surface gives speed + meteorological direction; converted to
  10u/10v via `u = -spd·sin(dir)`, `v = -spd·cos(dir)`. (CUON already supplies
  eastward/northward components, so no conversion upstream.)
- **Geopotential.** CUON reports `geopotential_height` in gpm; multiplied by
  g0 = 9.80665 to get `z` in m²/s², the ECMWF convention.
- **Vertical coordinate.** `z_coordinate_type == 1` means pressure in Pa; other
  types are dropped, and by default only Swift's 13 standard levels are kept
  (68,298 of 410,743 rows on the sample day).
- **Quality flags.** Default keeps flag 0 for surface (flags 0 and 2 largely
  duplicate each other — keeping both double-counts) and flag 2 for upper-air
  (the CUON sample is uniformly flag 2, so filtering on 0 would drop everything).

Validation on 2000-01-01 — the numbers came out physically right:

```
marine   8,185 reports   2t/2d/msl/sst/10u/10v
         dewpoint <= temperature in 2030 of 2031 pairs
         msl 959-1041 hPa, sst 270.7-312.0 K, |wind| <= 48 m/s
land   147,190 reports   9,178 SYNOP stations
upper   16,562 rows on standard levels
         mean geopotential height by level:
           1000 hPa -> 137 m     500 hPa ->  5574 m
            850 hPa -> 1460 m    250 hPa -> 10366 m
            700 hPa -> 3010 m     50 hPa -> 20352 m
```

Combined surface dataset (marine + land joined) builds to **155,375 rows**.

### CDS licence acceptance is programmatic

The land collection needs `global-land-observations-data-policy` (revision 2)
beyond the account defaults; without it the API returns
`403 required licences not accepted`. It can be accepted over the API:

```bash
curl -X PUT -H "PRIVATE-TOKEN: $KEY" -H "Content-Type: application/json" \
  https://cds.climate.copernicus.eu/api/profiles/v1/account/licences/global-land-observations-data-policy \
  -d '{"revision":2}'
```

`fetch_cds_obs.py` does this automatically on the first 403.

### GridSat: gridded, and the WV channel is era-dependent

NOAA NCEI, plain HTTPS, no credentials. 3-hourly granules
`GRIDSAT-B1.<YYYY>.<MM>.<DD>.<HH>.v02r01.nc`, so 00/06/12/18Z is an exact
subset. Native grid 0.07°, 5143 × 2000, **70°S–70°N** (no poles — inherent to
geostationary coverage). This confirms GridSat must use `layout: gridded`, not
`tabular`.

Channel availability, measured rather than assumed:

| year | `irwin_cdr` (11 µm) | `irwvp` (6.7 µm WV) |
|---|---|---|
| 1980 | 32–53 % | **0.0 %** |
| 1985 | 95.4 % | 37.3 % |
| 1995 | 75.0 % | 58.0 % |
| 2005 | 99.6 % | 99.6 % |

**`irwvp` does not exist before ~1985.** A 1980–2021 build will have an all-NaN
WV channel in the early years. `vschn` (0.6 µm) is excluded: it is a
reflectance, not a brightness temperature, and is night-masked.

Volume warning: ~4 MB/granule → ~6 GB per year at 6-hourly, ~250 GB for
1980–2021.

### AMSU-A is split across TWO records — you need both

There are two distinct NCEI archives whose paths differ only by a `-noaa`
suffix, and they are completely different products:

| | `.../amsu-a-brightness-temperature/` | `.../amsu-a-brightness-temperature-noaa/` |
|---|---|---|
| product | CICS L1C **swath** | NESDIS-STAR **FCDR-GRID** |
| channels | 4 window (23/31/50/89 GHz) | **11 sounding (4–14), incl. 57 GHz O₂** |
| resolution | per-orbit footprints, ~114 min | daily 1° means, split asc/desc |
| level | L1C | L3 |
| period | 1998–2021 | 1998–2021 |

Built as **two separate datasets** (`amsua-brightness-temperatures.yaml` and
`amsua-sounding-brightness-temperatures.yaml`) because mixing instantaneous
footprints with daily means in one dataset would be wrong. Between them they
cover all openly-available AMSU-A content.

The THREDDS catalog at `/thredds/catalog/cdr/nesdis-star-cdr-amsuA/` serves the
**same gridded files** — checked its 2010 listing, every entry is
`NESDIS-STAR_FCDR-GRID_AMSU-A_*`. It adds OPeNDAP/subsetting, not swath data.
No swath THREDDS catalog exists.

**Gridded channel availability is platform-dependent** (measured 2010-01-01):

| platform | channels | missing |
|---|---|---|
| AQUA | 5–14 | ch4 |
| M02 | 4–14 | — |
| N15 | 4–10, 12, 13 | ch11, ch14 |
| N16 | 5–14 | ch4 |
| N18 | 4–14 | — |

Combining all five is what populates all 11 channels; a single-platform build
silently drops some. Each (platform, node) contributes its own rows rather than
being averaged — different instruments, different local times. `platform` is
encoded numerically and `node` as 0/1, because the tabular writer's
`df.to_numpy(float32)` rejects string columns (the same trap `statid@hdr`
sprang). Ascending/descending are timestamped 06Z/18Z as **nominal placeholders
for the local-time split, not observation times** — these are daily means.

Physics confirms the sounding channels are real: BT falls ch5 (245 K) → ch9
(215 K) climbing through the troposphere, then rises ch10 → ch14 (250 K) into
the stratosphere — the classic oxygen-band weighting-function progression.

### AMSU-A swath record: only 4 of 15 channels

The CICS AMSU-A FCDR covers 1998–2021 and is openly accessible, but carries
only `23.8, 31.4, 50.3, 89.0 GHz`. Its sounding channels come from the gridded
record above instead.

The granules are also not CF-gridded: per-orbit swaths (857 scans × 30 pixels)
with data under `/Data_Fields` and geolocation under
`/Geolocation_Time_Fields`. xarray opens them as an *empty* dataset, so the
`netcdf:` source cannot read them — hence the flattener, which decodes
`scan_time_since98` (seconds since 1998-01-01; ~114 min orbit) and drops fill
values.

### AMSU-B, MHS, MSU: AWS Open Data, all channels complete

Found via the AWS open-data registry entry `noaa-cdr-fundamental`. All public
(anonymous HTTPS, no credentials, no boto3), all us-east-1:

| instrument | bucket | bucket coverage | Table 1 asks | channels |
|---|---|---|---|---|
| AMSU-B | `noaa-cdr-microwave-humidity-sounder-brit-temp-pds` | 1998–2025 | 1998–2014 | **5/5** |
| MHS | *same bucket* | 1998–2025 | 2005–2021 | **5/5** |
| MSU | `noaa-cdr-msu-brit-temp-pds` | 1978–2006 | 1980–2005 | **4/4** |

Unlike AMSU-A, these records are **complete** — the full channel set Table 1
specifies. Three traps, each verified against real granules:

- **AMSU-B and MHS share one bucket** and are separated only by filename
  (`NSS.AMBX.*` vs `NSS.MHSX.*`). `fetch_noaa_mw.py` filters by instrument.
- **MHS filenames change in 2016.** `NSS.MHSX.<plat>.D*` through 2015, then
  `CICS_V01R01-preliminary_MHS_FCDR_<plat>_D*` from 2016 to 2021. A glob
  matching only the old form **silently returns nothing after 2015** — this is
  what made 2016+ look empty on first inspection. Both parse identically.
- **Fill values differ between records**: AMSU-A uses `-999.0`, AMSU-B/MHS use
  `-99.0`, MSU uses `missing_value = -9999.0`. `mw_swath_to_wide.py` now reads
  `_FillValue` per variable and also clips to the documented `valid_min`/
  `valid_max` (10–400 K), because a `-99` averaged into a brightness
  temperature is not detectable downstream.

MSU differs structurally: flat CF netCDF rather than HDF5 groups, with
`Latitude`/`Longitude` as real variables and time from explicit
`Year`/`DayOfYear`/`MillisecondOfDay`. Note xarray promotes those coordinates
into `ds.variables` but **not** `ds.data_vars`, so an `in ds` membership test
misses them (this initially looked like "MSU has no geolocation"). MSU granule
coverage is also genuinely patchy — one 1990 partial orbit had 44 valid
footprints of 2288, the next had 858 of 858. That is the record, not a bug.

Physics checks passed: MSU brightness temperature falls monotonically from
ch1 (243 K, surface/window) to ch4 (210 K, stratosphere), as it should.

## Remaining ODB placeholders: no ODB data on this machine

Every recipe still has the placeholder `path: /path/to/odb/...`. A search of
`/lus/flare/projects/Swift-Reanalysis` and `/flare/datasets` found **no `.odb`
files at all**. Nothing can be built for real until the ODB feedback archive is
staged (or mounted) and `input.odb.path` is pointed at it.

To make progress anyway, `make_synthetic_odb.py` fabricates ODB files with the
same column schema the recipes query (`lat@hdr`, `lon@hdr`, `date@hdr`,
`time@hdr`, `varno@body`, `obsvalue@body`, `vertco_reference_1@body`,
`satid@hdr`). That is enough to exercise the SQL, the window logic and the pivot
— it is **a pipeline fixture, not science data. Never train on it.**

## Environment

`swift_env` was empty at the start. Installed:

```bash
pip install "anemoi-datasets[all]"          # 0.5.43 + xarray, zarr 2.18.7, codc/pyodc 1.6.0
conda install -c conda-forge odc            # 1.4.4 -- the CLI binary
```

The `odc` **command-line tool** is a hard requirement that is easy to miss: the
ODB source shells out to `odc sql` via `subprocess` (`create/sources/odb.py`,
`subselect_odb_using_odc_sql`). The `codc` Python package alone is not enough.

Swift itself is not yet installed into this env (it pins `zarr<3`; anemoi pulled
zarr 2.18.7, so they should co-exist — unverified).

## Three bugs found and fixed in the recipes

All ten recipes passed schema validation but **none of them worked**. Found by
building them against the synthetic archive.

### 1. Wrong window separator (fatal, all 10 recipes)

`window: "(-3h:+3h]"` → `ValueError: invalid window string`.
`anemoi.utils.window.Window` parses with `([\[\(])(.*),(.*)([\]\)])` — the
separator is a **comma**, not a colon. Fixed to `"(-3h,+3h]"` everywhere.

### 2. `group_by: monthly` silently discards ~98% of observations (all 10 recipes)

This is the dangerous one — it does not error, it just loses data.

In `OdbSource.execute` (`create/sources/odb.py:147-151`):

```python
for idate, (expanded_path, date_list) in enumerate(iterate_patterns(self.path, dates)):
    start = _add_dates(date_list[idate], ...)
```

`idate` counts **paths**, but it indexes **date_list**. With more than one date
per group, each expanded path is queried with the wrong analysis time, so every
file after the first returns no rows.

Measured on a 3-day synthetic archive:

| setting | rows kept |
| --- | --- |
| `group_by: monthly` | 15 of ~700 (98% lost, no error) |
| `group_by: 1` | all of them |

All recipes now pin `group_by: 1` with a comment explaining why. **Revert to
`monthly` only once the upstream loop pairs each path with its own date** —
`group_by: 1` means one ODB query per analysis time, which will be slow over
40 years and is worth fixing upstream before the full build.

### 3. `statid@hdr` is a string and aborts the build (2 conventional recipes)

`surface-synop-ships-buoys` and `upper-air-radiosonde-aircraft-amv` selected
`statid@hdr`, a character station id. The tabular writer does
`df.to_numpy(dtype=float32)` on the whole frame
(`create/tabular/result.py:162`), so it dies with
`could not convert string to float: 'S05409'`. Removed from both `select`
clauses. `satid@hdr` in the radiance recipes is numeric and is fine.
If station identity is needed, add a numeric surrogate in the ODB.

## varno codes: verified, and two were wrong

Fetched the authoritative table from <https://codes.ecmwf.int/odb/varno.csv/>
(the `.csv/` suffix on the codes site returns machine-readable output; the HTML
page is a JS shell). All codes now confirmed:

| code | name | description | used by |
|---|---|---|---|
| 1 | `z` | geopotential | upper-air |
| 2 | `t` | upper air temperature (K) | upper-air |
| 3 | `u` | upper air u component | upper-air |
| 4 | `v` | upper air v component | upper-air |
| 11 | `ts` | surface temperature (K) → **sst** | surface |
| 7 | `q` | specific humidity (q) | upper-air |
| 39 | `t2m` | 2m temperature (K) | surface |
| 40 | `td2m` | 2m dew point (K) | surface |
| 41 | `u10m` | 10m u component (m/s) | surface |
| 42 | `v10m` | 10m v component (m/s) | surface |
| 108 | `pmsl` | Mean sea-level pressure (Pa) → **msl** | surface |
| 119 | `rawbt` | brightness temperature (K) | all 8 radiance recipes |

Two corrections to the surface recipe:

- **msl was wrong: 110 → 108.** The template used 110, which is `ps` = surface
  pressure — a different quantity that varies with station elevation. Table 1
  asks for msl, which is 108 (`pmsl`).
- **sst was missing entirely.** No varno is literally named "sst"; the `where`
  clause had a TODO and omitted it. Ship/buoy SST is reported as 11 (`ts`,
  surface temperature) in conventional feedback. Alternative is 12 (`tsts`,
  "sea water temperature (used in synoptic maps)"), likely sparser — worth
  re-checking against the real archive.

The table also has instrument-specific radiance codes (248 `rawbt_hirs`,
250 `rawbt_hirs20`, 249 `rawbt_amsu`). We deliberately kept the generic 119;
widen to e.g. `varno@body in (119, 249)` if the real archive stores them apart.

## EUMETSAT Data Store: the two FDRs are reachable

HIRS and SSM/T-2 come from EUMETSAT rather than ECMWF. Resolved to Data Store
collection ids via the OpenSearch API:

| Table 1 entry | collection | title | coverage | vs. Table 1 |
|---|---|---|---|---|
| HIRS | `EO:EUM:DAT:0961` | HIRS L1C FDR Release 2, Multimission | 1978-11-03 … 2022-12-31 | covers 1980–2021 ✓ |
| SSM/T-2 | `EO:EUM:DAT:0343` | SSM/T-2 Microwave Humidity Sounder CDR Release 2, DMSP | 1994-07-05 … 2005-01-02 | covers 1994–2005 ✓ |
| ATMS | `EO:EUM:DAT:0345` | ATMS L1C CDR Release 1, Suomi-NPP | 2011-12-10 … 2018-12-31 | **short: no 2019–2021** |

**Watch out for `EO:EUM:DAT:0964`** — it is titled "SSM/T Level 1C FDR" and
looks like a match, but SSM/T is a *temperature* sounder (1991–2005), a
different instrument from SSM/T-2. Use 0343.

**ATMS falls three years short.** Release 1 stops at end-2018 but Table 1 asks
for 2012–2021. Sources checked and ruled out for 2019–2021:

| candidate | verdict |
|---|---|
| AWS `noaa-jpss` | only VIIRS and OMPS under SNPP/NOAA20 — no ATMS |
| AWS `noaa-cdr-microwave-temp-sounder-brit-temp-pds` | misleading name; actually AMSU-A (`CICS_V00R01_AMSUA_*`) |
| NCEI `cris-atms-environmental-data-record` | 2017 only |
| `EO:EUM:DAT:MULT:EARS-ATMS` | **not in the Data Store** — "Collection not found" |
| `EO:EUM:DAT:MULT:ATMSSDR` | **not in the Data Store** — "Collection not found" |

The last two are worth explaining, since their catalogue pages exist on the user
portal and look like valid products. Both return `Collection not found` from
`/data/browse/1.0.0/collections/<id>`, and neither is among the 188 browsable
collections. That is not an API quirk on our side: `EO:EUM:DAT:MULT:HIRSL1`
returns 200 through the identical endpoint, so the `MULT:` namespace works.
EARS is EUMETSAT's regional **near-real-time relay**, distributed over EUMETCast
rather than archived — a live feed, not a reanalysis-length record. The portal
catalogue lists products across all distribution channels, so a page there does
not imply Data Store availability.

**`EO:EUM:DAT:0345` is the only ATMS collection in the Data Store.**

### NOAA CLASS is network-blocked from this machine

CLASS holds the ATMS SDR/TDR records that would cover 2019–2021, and the user
has an account, but the host is unreachable from the Aurora login node:

```
www.class.noaa.gov      DNS resolves (137.75.118.173), TLS reset by peer
www.aev.class.noaa.gov  DNS resolves, TLS reset by peer
```

Port 80 answers and issues `302 -> https://www.aev.class.noaa.gov/`, but the
HTTPS handshake is then reset — the server sends a ServerHello and the
connection dies before the certificate (`Cipher is (NONE)`, `write:errno=104`).
Both TLS 1.2 and 1.3 fail identically.

This is environmental, not a CLASS outage or a client bug: from the same shell,
`www.ncei.noaa.gov`, the AWS CDR buckets, `api.eumetsat.int` and
`cds.climate.copernicus.eu` all return 200. Something between here and CLASS is
dropping the connection.

Options for ATMS 2019–2021, in rough order of effort:

1. **Accept 2012–2018.** Seven of the ten years, no extra work. The recipe
   already documents the shortfall.
2. **Download from CLASS off-cluster** (laptop or a host with open egress) and
   stage the files onto `/lus/flare`. CLASS is order-based — you request a
   subset, it emails when the order is staged — so it is a manual step
   regardless of network access.
3. **Ask ALCF support to allow egress** to `*.class.noaa.gov` if this is a
   site firewall rule.
4. **Use ECMWF ODB feedback** (varno 119) if ODB access ever materialises.

Access, established by probing the API:

- **Search and metadata are public** — no credentials.
  `https://api.eumetsat.int/data/search-products/1.0.0/os?format=json&pi=<collection>&dtstart=…&dtend=…`
- **Product download needs OAuth2 client-credentials.** Unauthenticated download
  returns a misleading WSO2 `404 No matching resource found` rather than a 401.
- `eumdac` 3.1.1 installed as the official client.

**Credential type matters.** These are OAuth2 *consumer key + consumer secret*
(generated at <https://api.eumetsat.int/api-key/>), **not** the portal
username/password — `eumdac.AccessToken` takes `(consumer_key, consumer_secret)`
and the token endpoint rejects anything else with `invalid_client`. Register
them once with:

```bash
eumdac set-credentials <consumer_key> <consumer_secret>
```

which writes `~/.eumdac/credentials` (0600). Prefer that over exporting
env vars or passing `-u user:pass` to curl — on a shared login node a password
in a command line is visible in `ps` to every other user. **Credentials are
registered and all three EUMETSAT datasets download successfully.**
`eumetsat_search.py` reads that file first and falls back to env vars.

### The EUMETSAT records are the easy ones to parse

Unlike the NOAA microwave swaths, all three are proper CF netCDF with a
`channel` dimension, 2-D `latitude`/`longitude` and a per-scanline `time` — so
one converter (`eumetsat_fcdr_to_wide.py`) handles all of them. The only
difference is the variable name:

| instrument | collection | BT variable | channels |
|---|---|---|---|
| HIRS | `EO:EUM:DAT:0961` | `btemps` | 20 |
| SSM/T-2 | `EO:EUM:DAT:0343` | **`tb`** | 5 |
| ATMS | `EO:EUM:DAT:0345` | `btemps` | 22 |

Granules arrive as `.zip` from the Data Store; the converter accepts either the
zips or extracted `.nc`. HIRS is multimission, so several NOAA/Metop platforms
(and three HIRS generations) coexist on any given day. SSM/T-2 also carries a
`(channel, channel)` correlation matrix that trips an xarray duplicate-dimension
warning — harmless for the variables we read.

`work/eumetsat_search.py` wraps this: `--list` browses collections, default
describes the two needed, `--collection ssmt2 --start … --end …` searches, and
`--download` fetches (credentials required). Verified against 1998-01-01:
20 SSM/T-2 granules found, F12/F14 platforms.

Note these arrive as netCDF granules, not ODB. The recipes currently assume ODB
ingestion — see open item 4.

## Verified working

**Built from real data** (2000-01-01 for the CDS products, 1980-01-01 for
GridSat, 1998-10-26 for AMSU-A):

| dataset | rows / shape | columns |
|---|---|---|
| surface (marine + land) | 155,375 | 2t, 2d, msl, sst, 10u, 10v |
| upper-air (CUON) | 16,562 | pressure, z, t, u, v, q |
| GridSat | 4 × 2 × 10,286,000 | irwin_cdr, irwvp |
| AMSU-A window (swath) | 24,270 | bt_23, bt_31, bt_50, bt_89 |
| AMSU-A sounding (grid) | 322,416 | bt_4..bt_14 (11/11) + platform, node |
| AMSU-B (AWS) | 159,120 | bt_1..bt_5 (5/5) |
| MHS (AWS) | 210,780 | bt_1..bt_5 (5/5) |
| MSU (AWS) | 869 | bt_1..bt_4 (4/4) |
| HIRS (EUMETSAT) | 35,056 | bt_1..bt_20 (20/20) |
| SSM/T-2 (EUMETSAT) | 280,172 | bt_1..bt_5 (5/5) |
| ATMS (EUMETSAT) | 214,176 | bt_1..bt_22 (22/22) |

**All 11 recipes build from real data** (10 Table 1 rows, with AMSU-A split into
window + sounding), each with the full channel set its source provides.
`make_synthetic_odb.py` and the synthetic fixture are off the critical path now,
but kept: they are the only way to exercise the `odb:` source if you later gain
ODB access.

`combine.yaml` was rewritten to reference the real dataset names — the original
`obs-ea-ofb-*` names it listed never existed as built datasets. Verified: every
reference now resolves to a recipe's `name:`. GridSat is deliberately excluded
(it is `layout: gridded`, so it cannot be zipped onto tabular windows).

## Scaling up: the 2010 pilot

Decision: **stream and discard raw granules**, build **one full year (2010)**
across all datasets first, and pace CDS **monthly and sequentially**.

### Storage: the project quota is 5 TB, not what `df` first suggests

`df -h /lus/flare` reports 91 PB / 31 PB free — that is the whole shared
filesystem. The number that binds is the **project quota**:

```
lfs quota -p 20744 /lus/flare  ->  5 T quota, 5.5 T hard limit
```

Measured raw source volume for the full 1980–2021 period is **~8.7 TB**, which
does not fit. Hence streaming: `scale_download.py` fetches each granule to a
temp dir, converts it to points, writes parquet, and deletes the raw file. Only
GridSat keeps its raw netCDF (it is the gridded dataset — its recipe reads the
netCDF directly, so discarding it would destroy what the recipe needs).

Measured per-year volumes from real listings, not guesses:

| year | AMSU-B + MHS bucket |
|---|---|
| 1998 | 958 objects, 4.0 GB |
| 2005 | 18,732 objects, 83.0 GB |
| 2010 | 31,036 objects, **117.1 GB** |
| 2016 | 15,394 objects, 63.5 GB |
| 2021 | 14,985 objects, 45.7 GB |

### Full-period projection, from measured 2010 sizes

Once the pilot year was on disk the estimates could be replaced with real
numbers. Per-dataset 2010 output, multiplied by each instrument's actual
operating span:

| dataset | GB/yr (measured) | years | total |
|---|---|---|---|
| MHS | 88.6 | 17 | 1.51 TB |
| AMSU-B | 55.5 | 17 | 0.94 TB |
| GridSat (stripped) | 22.5 | 42 | 0.94 TB |
| AMSU-A swath | 10.9 | 24 | 0.26 TB |
| AMSU-A gridded | 2.8 | 24 | 0.07 TB |
| land | 1.2 | 42 | 0.05 TB |
| marine | 0.3 | 42 | 0.01 TB |
| upper-air | 0.2 | 42 | 0.01 TB |
| **measured subtotal** | | | **3.80 TB** |
| HIRS, MSU, SSM/T-2, ATMS (estimated from day samples) | | | ~0.12 TB |
| **full period** | | | **~3.9 TB** |

Two surprises versus the earlier guesses: **MHS came in at 2x the estimate**
(88.6 GB/yr, 3.29 billion rows for 2010 — the largest dataset by far), while
**AMSU-A swath came in at half** (10.9 vs 22 GB/yr). The conventional obs are
negligible: land is 129.8 M rows in 1.16 GB for the whole year.

At ~3.9 TB the full period would have fitted the original 5 TB quota, but with
only ~20% headroom — no room for a reprocess, a second resolution, or keeping
raw. **A 20 TB extension has been requested**, which takes it to ~20% utilised
and removes the constraint. Note the projection assumes GridSat stays stripped
and that raw granules continue to be streamed and discarded; keeping raw would
add ~8.7 TB.

2010 pilot: **~155 GB** after GridSat stripping (~3% of quota) — GridSat 19 GB,
AMSU-B 61, MHS 44, AMSU-A swath 22, AMSU-A grid 9, CDS products ~3.3.

Full period after stripping is roughly **3–4 TB against the 5 TB quota** — it
fits, but not with much room. GridSat dropped from ~2.9 TB to ~0.8 TB, which is
what made the difference. Worth re-checking once a full year of every instrument
is on disk and the per-year figures are measured rather than extrapolated.

### Parquet, not CSV, for intermediates

CSV is *larger than the source netCDF* for the swath records — measured 4.2× for
AMSU-B. Parquet+zstd is 40–87% smaller than the equivalent CSV. Note even
parquet is ~108% of the raw netCDF for AMSU-B: the data is genuinely
high-entropy (6.3 M footprints/day), so there is little left to squeeze without
quantising (int16 at 0.01 K halves it again, but that is lossy and not enabled).

### Four bugs found while scaling

1. **GridSat had no converter branch** — `convert()` raised `ValueError: gridsat`
   for every granule, silently producing nothing for two minutes before I
   checked. GridSat should never have been in the streaming script at all; it is
   now explicitly excluded with an error message that says why.
2. **Temp files lost their filenames.** `tempfile.NamedTemporaryFile` gave names
   like `tmpi8u7dlpw.nc`, but the gridded AMSU-A converter parses platform, date
   and ascending/descending *out of the filename* — so every granule came back
   "unparseable name". Now downloads into a scratch dir under the real basename.
3. **AMSU-A swath day-token was wrong.** Its files use `_D10001_`
   (underscore-delimited), not the dotted `.D10001.` of the AMSU-B naming. The
   pattern matched nothing and the run reported 0 rows without erroring.
4. **`if "NSS"` was always truthy** — a leftover conditional in the day-token
   logic that happened to work by accident.

### CDS: a 403 that is really a size limit

A full month of all six marine variables is rejected with:

```
403 Client Error: Forbidden ... cost limits exceeded
Your request is too large, please reduce your selection.
```

The 403 is misleading — it reads like a permissions or licence problem (and we
had a genuine licence 403 earlier), but it is a per-request cost cap. Measured
on 2010-01: 3 vars × 31 days OK, 6 vars × 10 days OK, 6 × 31 rejected.
`scale_cds.py` therefore splits the variable list into batches of 3 and merges
the long-format frames before pivoting — the batches are disjoint in
`observed_variable`, so the full variable set reassembles per report. Verified:
2010-01 marine gives 992,186 rows with all six variables populated.

### GridSat: 11 large arrays, of which the recipe reads 2

GridSat is 0.07° — 5143 × 2000 = 10.3 M points, 70°S–70°N. That is ~20× finer
than Swift's 1.40625° grid.

It cannot usefully be *recompressed*: the provider already stores int16 with
scale/offset plus zlib, so generic compression is spent. But each granule
carries **11 large (2000 × 5143) arrays and the recipe uses two**
(`irwin_cdr`, `irwvp`). The rest — `irwin_2`, `irwvp_2`, `vschn`,
`satid_ir/wv/vs`, `irwin_vza_adj` … — are dead weight.

`gridsat_strip.py` drops them, **losslessly**:

| | per granule | 2010 | 1980–2021 |
|---|---|---|---|
| as distributed | 57.7 MB | 73 GB | ~2.9 TB |
| stripped | 15.4 MB | **19 GB** | **~0.8 TB** |

The provider's int16 encoding is preserved and every granule is round-trip
verified before its original is replaced (worst observed difference 1.95e-05 K,
five orders of magnitude under the 0.01 K quantum). Verified the recipe still
builds from stripped granules and returns the same values.

**Downscaling was considered and rejected** — worth recording so it is not
revisited blindly. It saves far more (0.28° → ~2 GB/yr, 1.40° → ~0.1 GB/yr) and
preserves the mean and most of the variance, *but mean-pooling destroys the
cold-cloud tail*:

| | BT < 210 K (deep convection) |
|---|---|
| native 0.07° | 0.28% of pixels |
| 10× (0.70°) | 0.17% |
| 20× (1.40°) | 0.09% |

Two-thirds of the strongest convective signal averaged away at 20×, while mean
and σ still look healthy — the kind of loss that does not show up in summary
statistics. If disk pressure ever forces coarsening, store **min alongside
mean**: min-pooling preserves the coldest value exactly (184.3 K at every
scale). For now the native grid is retained.

### Land is the heavy one: 11 GB RSS per monthly pivot

The CDS land product is ~9x denser than marine (348,553 rows/day vs ~31,000) and
its monthly archives are 2.5-3.4 GB against marine's ~40 MB. `scale_cds.py`
loads a whole month of long-format CSV into memory before pivoting, which was
measured at **11.1 GB RSS** and several minutes pinned at 100% CPU per month.

That is survivable on a login node for the pilot, but it is a ceiling to design
around before the full 42-year run -- pivot per-day rather than per-month, or
chunk the read. Worth noting the process looks hung during this phase: I/O drops
to zero for minutes while it is purely CPU-bound. Check CPU ticks, not rchar,
before concluding a CDS job has stalled.

### Helper scripts added

| script | role |
|---|---|
| `scale_download.py` | stream S3/NCEI granules → parquet, raw discarded, checkpointed |
| `scale_cds.py` | CDS month-by-month with variable batching, checkpointed |
| `gridsat_strip.py` | drop unused GridSat variables, round-trip verified, resumable |

Both skip work whose output already exists, so an interrupted run resumes by
re-issuing the same command.

## 2010 pilot: COMPLETE

All eight streamed datasets finished, no gaps, 182 GB total.

| dataset | files | GB | coverage |
|---|---|---|---|
| MHS | 365 | 88.6 | 20100101–20101231, no gaps |
| AMSU-B | 365 | 55.5 | no gaps |
| GridSat | 1460 | 22.5 | 4/day, stripped |
| AMSU-A swath | 365 | 10.9 | no gaps |
| AMSU-A gridded | 365 | 2.8 | no gaps, 11 channels, 5 platforms |
| land | 365 | 1.2 | 129.8 M rows |
| marine | 365 | 0.3 | 11.3 M rows |
| upper-air | 365 | 0.2 | 6.4 M rows |

Row counts per day at mid-year: MHS 8.97 M, AMSU-B 6.22 M, AMSU-A 2.03 M,
AMSU-A grid 322 k, land 351 k, marine 34.5 k, upper 17.8 k.

Sanity checks pass. One thing looked wrong and is not: AMSU-B and MHS have BT
values down to 74 K and 99 K. Only ~0.1% fall below 150 K (0.001 percentile
128 K / 135 K), and the 183/89 GHz humidity channels genuinely reach very low
brightness temperatures over deep convection. The values are inside the FCDR's
own `valid_min` of 10 K, so they are kept unfiltered.

### BLOCKER: the `csv:` source cannot read parquet

The scaled output is parquet, but anemoi's `csv:` source tries to UTF-8 decode
whatever path it is given:

```
💣 'utf-8' codec can't decode byte 0xc0 in position 7: invalid start byte
```

So **the recipes cannot consume the scaled pilot output as-is**. The options:

1. **Convert parquet → CSV at build time.** Measured: one AMSU-B day is 164.8 MB
   parquet → 546 MB CSV (3.3x), 55 s to write. A full AMSU-B year would be
   ~199 GB of CSV against 55.5 GB parquet, and the full period would blow past
   10 TB — which is exactly what choosing parquet avoided.
2. **Teach anemoi to read parquet** — add a `parquet:` source, or extend `csv:`
   to dispatch on extension. Small change (`create/sources/csv.py` is ~130
   lines) and it keeps the storage win.
3. **Write a custom source** in the recipe pointing at the parquet directly.

Option 2 looks right and is the smallest lasting fix. Nothing is lost either
way — the pilot data is complete and correct, it just is not yet readable by the
build step.

## NNJA: the gridding approach, developed here

`gs://gcp-nnja-ai/data/v1/` -- 14 datasets, hive-partitioned parquet, one file
per day:

```
data/v1/<group>/<subtype>/<NCxxxxxx>/OBS_DATE=YYYY-MM-DD/gdas.YYYYMMDD.NCxxxxxx.parquet
```

with `catalog.json` at the root and a `.pmetadata` schema per dataset. Public:
read anonymously with `gcsfs.GCSFileSystem(token="anon")`, no credentials, and
reachable from the Aurora login node (unlike CLASS). `pyarrow` 25 + `gcsfs` in
`swift_env` are sufficient; the official `nnja-ai` client is not required.

Working dir: `/lus/flare/projects/Swift-Reanalysis/work/nnja/`, with its own
`README.md`. `nnja_grid_pilot.py` is the builder.

### It is already pivoted -- this is the main win

The whole `*_to_wide.py` layer exists because CDS/NOAA/EUMETSAT ship long-format
or HDF5-grouped swaths and anemoi's `csv:` source cannot pivot. NNJA ships
levels and channels as **separate columns** already:

```
TMDB_PRLC85000, GP10_PRLC50000, ...    (adpupa, 264 columns)
BRITCSTC.TMBR_00001 .. _00015          (amsua, 48 columns)
```

### Coverage, measured

| dataset | NNJA period | note |
| --- | --- | --- |
| conv/adpsfc NC000001 (SYNOP) | 1979-01-01 .. present | **hole 2000-2004** (0 days 2000-03, 3 in 2004, 137 in 2005) |
| conv/adpupa NC002001 (radiosonde) | 2010-01-01 .. present | vs CUON's 1980 in the ODB path |
| amsua | 1998-10-25 .. 2025-03-31 | |
| mhs | 2007-02-27 .. 2025-03-31 | |
| atms | 2012-02-15 .. 2025-03-31 | covers what EUMETSAT's 0345 could not |
| iasi / cris / geo / seviri | 2008 / 2018 / 2019 / 2022 onward | **not in scope**, see below |

**Five Table 1 instruments have no NNJA equivalent**: AMSU-B, HIRS, MSU,
SSM/T-2, GridSat. All five were brightness temperature only, so no *physical
variable* is lost, but the era coverage is:

| absent | channels | period | consequence |
| --- | --- | --- | --- |
| HIRS | 20 IR | 1980-2021 | the only full-period sounder |
| MSU | 4 MW | 1980-2005 | pre-AMSU microwave temperature |
| SSM/T-2 | 5 MW | 1994-2005 | DMSP microwave humidity |
| AMSU-B | 5 MW | 1998-2014 | microwave humidity before MHS starts 2007 |
| GridSat | irwin_cdr, irwvp | 1980-2021 | gridded IR window + WV |

NNJA's earliest satellite data is 1998-10-25 and adpupa starts 2010, so **NNJA
alone cannot support a reanalysis reaching back to 1980.** If the full period
matters, the AIFS-DOP sources above are still the way to get pre-1998.

**CrIS and IASI are NOT in scope.** They are hyperspectral IR sounders (431 and
616 channels), are **not** in Table 1, and were only priced during exploration.
They would dominate any capacity estimate (~31 TB and ~19 TB raw) and are
radiance (`W m**-2 sr**-1`), not brightness temperature like everything else
here. Do not let them into a volume projection.

### Store the grids, not the observations

Observations are binned onto Swift's grid at build time and the raw parquet is
**streamed and discarded**. Grid: 128 x 256 at 1.40625 deg, latitude
**descending** 89.296875 .. -89.296875, longitude 0 .. 358.59375 -- the WB2
convention, verified against
`/flare/datasets/wb2/0.25deg_1_step_6hr_h5df_fix_bug/lat.npy`.

Each variable is written as `input/<name>` plus companion planes:

| plane | dtype | meaning |
| --- | --- | --- |
| `<name>` | float32 | cell mean, NaN where unobserved |
| `<name>__cnt` | uint16 | observations in cell (0 = no data) |
| `<name>__min` / `__max` | float32 | radiance datasets only |

The count plane is what keeps the encoding honest: without it nothing
distinguishes "observed to be 291 K" from "not observed".

Min/max exist because mean-pooling erases the cold tail -- the same finding as
the GridSat downscaling analysis above. Deep convection is the *coldest
footprint* in a cell, not the average. MHS ch1, 2010-06-15 00Z:

| threshold | cells by mean | cells by min |
| --- | --- | --- |
| < 210 K | 3,806 | 5,862 (1.5x) |
| < 200 K | 2,614 | 3,440 (1.3x) |
| < 190 K | 2,077 | 2,525 (1.2x) |

Coldest cell mean 142.8 K against a coldest footprint of 134.8 K. Conventional
obs do not get extrema; a cell mean of station temperatures is the quantity of
interest.

**Storage: 22x smaller than keeping the observations.**

| dataset | gridded GB/yr | raw GB/yr | ratio |
| --- | --- | --- | --- |
| adpsfc | 0.190 | 1.4 | 7x |
| adpupa | 0.398 | 0.7 | 2x |
| AMSU-A | 5.56 | 22.2 | 4x |
| MHS | 2.00 | 65.9 | **33x** |

2010 pilot ~8.1 GB, against **182 GB for the equivalent AIFS-DOP pilot**. Grid
cost is `channels x 128 x 256` regardless of observation density, so the densest
instruments win biggest. Full period for the Table 1 overlap (AMSU-A 27 y, ATMS
13 y, MHS 18 y, conv) is **~0.3 TB, about 6% of the 5 TB quota** -- the 20 TB
extension is not needed for this scope.

### All 69 Swift variables are produced

Swift predicts 69 channels: 4 surface + 5 upper-air variables on 13 levels, plus
3 input-only forcings. Verified programmatically against
`swift.data.constants.VARS`: **69/69, no missing, no extras.** Output uses
Swift's own names (`temperature_600`, `specific_humidity_850`) so the h5 groups
are addressable straight from `VARS`.

Two conversions were needed:

**Specific humidity.** NNJA radiosondes report dewpoint (`TMDP_PRLC*`), not `q`.
Saturation vapour pressure *at the dewpoint* is the actual vapour pressure by
definition, so Bolton (1980) eq. 10 gives it directly, and pressure is the level
itself:

```
e = 611.2 * exp(17.67*Tc / (Tc + 243.5))      [Pa]
q = 0.622*e / (p - 0.378*e)
```

Validated at 1000 hPa against psychrometric tables: 0.3-3.1% error (30 C ->
26.84 g/kg vs ~27.7; 0 C -> 3.81 vs ~3.8). Clamped to `0 < q < 0.1 kg/kg` --
bad dewpoint reports can give e > p, which is unphysical rather than numerical.
Gridded output falls off with height exactly as it should: 7.59 g/kg at 1000 hPa
-> 0.75 at 500 -> 0.04 at 100.

**600 hPa.** Not a WMO mandatory level, so it is absent from the NNJA schema and
is interpolated from 700 and 500 hPa, **linear in log(p)** (geopotential is
linear in log-p for an isothermal layer, via the hypsometric equation; weight
0.4581). Against the US Standard Atmosphere: Z 3012/5574 m -> 4186 m (ref 4206,
-20 m); T 268.6/252.4 K -> 261.18 K (ref 261.0). NaN in either bracket
propagates, so a profile missing a mandatory level gets no 600 hPa value rather
than a one-sided guess. Verified in the built grids that every 600 hPa field
sits between its brackets.

Ordering matters: **winds are converted to u/v before interpolating.**
Interpolating a direction in degrees across the 0/360 wrap would be garbage.

### The 00Z window bug -- read before touching the window logic

A 00Z analysis window spans `(21:00 previous day, 03:00 this day]`, so it is fed
by **two** daily parquet files. The first version processed each day
independently and wrote 00Z from whichever day touched it last, so the previous
day's 21:00-24:00 tail *overwrote* rather than joined the 00:00-03:00 head.

It did not error. It kept ~23% of the data:

```
Jun 15 parquet, rows belonging to Jun 15 00Z : 12,814
Jun 15 parquet, rows belonging to Jun 16 00Z :  3,911
what the 00Z h5 actually contained           :  3,940   <- tail only
```

06/12/18Z were unaffected. `run_dataset` now carries the 00Z accumulator across
the day boundary and flushes only once both contributing days are read. After
the fix the four analysis hours are balanced (adpsfc 2010 medians: 00Z 16,850 /
06Z 17,383 / 12Z 17,384 / 18Z 17,010).

**This is the same failure shape as the `group_by: monthly` bug** -- no
exception, plausible summary statistics, most of the data silently gone. After
touching windowing, check per-analysis-hour counts, not just totals.

### 2010 pilot results

| dataset | windows | obs coverage per 6h window |
| --- | --- | --- |
| adpsfc | 1461 / 1461 | 11.2% of cells |
| adpupa | 1461 / 1461 | ~1.0% per level |
| AMSU-A | 1457 / 1461 | **97.0%** |
| MHS | (running) | **88.6%** |

The radiances are what make a dense grid viable at 1.4 deg; conventional obs
alone cannot drive an autoregressive model.

Validation on the completed conventional year:

- Seasonal cycle correct and hemispherically opposed -- adpsfc 2t NH Jan 268.25
  -> Jul 294.94 K (+26.69), SH Jan 293.22 -> Jul 281.02 (-12.20).
- Annual-mean radiosonde profile matches climatology, including the
  **stratospheric inversion**: 100 hPa 209.31 K -> 50 hPa 213.54 K. Temperature
  rising above the tropopause is the signature that the vertical coordinate is
  not scrambled.
- Geopotential heights: 1000 hPa 111 m, 850 1462, 700 3035, 500 5642, 250
  10508, 50 20566 m.

### Two things that look like bugs and are not

1. **The 4 missing AMSU-A windows are real upstream gaps.** 2010-05-16 12Z,
   11-17 12Z, 12-21 06Z and 12Z have zero rows in the source parquet -- those
   days carry no observations between hours 10 and 20 (2010-12-21 has only hours
   0-3 and 21-23). Not a code failure. **The archive is not gapless, so the
   dataset class must tolerate missing windows** rather than assume a dense
   6-hourly sequence.
2. **Wild temperature outliers are raw-BUFR noise, not a gridding artefact.**
   2010 adpsfc `2t` spans 173.6-372.5 K, but implausible cells are **0.0088%**
   of the sampled total (48 of 543,915) and nearly all are single-observation
   (`__cnt == 1`). NNJA is raw BUFR, not QC'd reanalysis feedback. **Filter on
   `__cnt` or clip to a physical range before training** -- the count plane
   makes this easy, which is part of why it is stored.

## Radiances have nowhere to go, and why that picks the source

### Swift's 69 are input AND target

`data/era5.py:211-212` is unambiguous:

```python
x = self._load_file(self.files[idx],     self.variables + self.forcings)  # 72 ch
t = self._load_file(self.files[idx + …], self.variables)                  # 69 ch
```

The same 69 variables appear on both sides -- Swift is autoregressive, so `x` is
the full state at time *t* and `t` is the state at *t+delta* (or the residual).
`n_condition_channels = 69 + 3 forcings = 72`. The only input-only channels are
the 3 forcings.

Two consequences, and the second is the decisive one.

**Sparsity is worse than it looks.** A ~1%-filled `specific_humidity_500` is not
merely a thin training signal -- it is a nearly empty *input state* the model
must autoregress from. ERA5 hands Swift a complete field every step;
observations do not, at any resolution, from any source. This is the core
difficulty of the whole observation-training idea and it is not solved by
choosing a better dataset.

**There is no slot for a radiance.** A brightness temperature is an *observation
of* the state, not a component of it, and not a known forcing:

| slot | semantics | can a radiance go here? |
| --- | --- | --- |
| `variables` (69) | input **and** prediction target | no -- the model would have to predict BT as part of its state |
| `forcings` (3) | input-only, static/known at inference (TOA solar, surface geopotential, LSM) | only by abusing the contract |

The three options were:

1. **Radiances as extra forcing channels.** Cheapest, but a conceptual abuse --
   forcings are assumed known at inference, and it would prop up the input with
   97%-covered BT while the 69 state channels stay 1-11% filled.
2. **Radiances via an observation operator / DA-style loss.** Physically right,
   needs a forward model state -> BT. Substantially more work.
3. **No radiances; train on the state variables alone.** *(chosen)*

### Option 3 chosen -- which reverses the source decision

With radiances out of scope, NNJA's advantage evaporates: its radiances were the
reason to prefer it. For the 69 state variables the AIFS-DOP conventional pair is
**strictly better**:

| | NNJA | AIFS-DOP (CDS) |
| --- | --- | --- |
| upper air | `conv/adpupa`, **2010**+ | **CUON, 1901-2024** (verified via CDS catalogue) |
| 600 hPa | absent, interpolated from 700/500 | **native** -- `work/wide/upper_all.csv` carries all 13 levels |
| specific humidity | derived from dewpoint (Bolton) | **native `q` column** |
| surface | `conv/adpsfc`, 1979+, **hole 2000-2004** | CDS marine + land, 1980-2021, no hole |

So the two datasets that produce the 69 are:

| AIFS-DOP dataset | source | gives |
| --- | --- | --- |
| `upper-air-radiosonde-aircraft-amv` | CDS CUON | z, t, u, v, q x 13 levels = 65 |
| `surface-synop-ships-buoys` | CDS marine + land | 2t, 10u, 10v, msl (+2d, sst) = 4 |

Both are already wired to real open data and need only `~/.cdsapirc` -- no ODB,
no EUMETSAT OAuth2, no CLASS. **The five instruments NNJA lacks (HIRS, MSU,
SSM/T-2, AMSU-B, GridSat) are all radiances and are therefore also out of
scope** -- they contribute nothing to the 69.

The CUON recipes are curated 1980-2021, but the collection itself runs
1901-2024, so **extending the start to 1979 is a recipe date change, not a new
source**. The CDS surface collections need the same check.

### What carries over from the NNJA work

The gridding machinery is source-agnostic and is the reusable part:

- `nnja_grid_pilot.py` -- the 6-hour windowing (including the 00Z day-boundary
  fix), the WB2 grid convention, the `__cnt` sparsity planes, the h5 layout
  using Swift's own variable names
- the storage result: gridding is ~22x smaller than keeping observations
- the 2010 pilot as a reference build and a correctness baseline

**Done (2026-09-22):** the `amsua`/`mhs` dataset definitions and the `_b_radiance`
builder were removed from `nnja_grid_pilot.py`, and the 2010 radiance grids
(~6.9 GB) were deleted -- this first evaluation is state variables only.
Expanding the architecture to take radiances is a later conversation; the
measurements above (97.0% / 88.6% coverage, the min/max tail recovery) are the
record of what was learned, and the `__min`/`__max` accumulator path is kept in
the code, unused, behind `extrema=True` so it need not be rediscovered.

Surviving pilot output is `grids/adpsfc` and `grids/adpupa`, 1461/1461 windows
each, 709 MB total, verified 69/69 variables.

Retargeting means pointing the same gridder at the CUON / CDS surface wide CSVs
instead of GCS parquet -- the `build` functions change, the accumulation,
windowing and writing do not.

## Open item 7: the ingest path (implemented, verification in progress)

**Decisions**: dense climatology-imputed input + loss masked to observed cells;
4 surface variables first; 6h step, because 6h *is* the reanalysis cycle. The
design follows AIFS-DOP (arXiv:2606.19093): every published observation-trained
forecaster densifies the input and masks the loss, and the masked loss is
precisely what lets the network emit -- and therefore autoregress -- a full
field. Where that asymmetry is skipped the literature reports failure: DAWP
(2510.15978) measured training diverging at ~20k steps without it, Huracan
(2508.18486) names zero-filling as the cause of its weak pressure skill.

### What was built

| file | role |
| --- | --- |
| `swift/src/swift/data/era5_obs.py` | `ERA5ObsDataset` + `ERA5ObsRollOutDataset` |
| `swift/src/swift/training/loss.py` | `w_obs` observation weight in all 5 losses |
| `swift/src/swift/training/validate.py` | rollout RMSE made mask-aware |
| `swift/src/swift/train.py` | rollout class follows the train dataset's module |
| `swift/src/swift/configs/{data/obs-nnja-1.4,experiment/obs-nnja-swinv2-1.4-scm}.yaml` | configs |
| `swift/scripts/aurora-obs{,-check}.sh` | PBS jobs (project `Swift-Reanalysis`, `debug`) |
| `work/nnja/make_splits.py` | chronological train/val/test symlinks |
| `work/nnja/make_norm_stats.py` | stats over observed cells + `obs_freq.npz` |
| `work/nnja/eval_masked.py` | masked RMSE vs persistence |
| `work/nnja/h5_downgrade.py` | HDF5 format repair (see below) |

The mask reaches the loss as a **climatological** `w_obs` buffer built from
`dataset.observation_weight()`, duck-typed so dense ERA5 gets a scalar 1.0 and
is unaffected. This needs no change to the batch tuple or any loss signature,
and the network is near-fixed (6h mask IoU 0.902; 84% of obs in 9.6% of cells).
A `weight_floor` of 0.02 keeps ~14% of the loss mass on never-observed cells --
without it the model gets no gradient at all across 87% of the grid, yet must
emit values there which feed straight back in as the next input. The deliberate
approximation: a usually-observed cell missing in a given window still
contributes a down-weighted spurious residual. Upgrade path if results are
ambiguous is a true per-sample mask, which does need the batch contract changed.

### Three environment traps

1. **Three modules, not one.** `swift_env` has no torch. Torch 2.10 + IPEX are
   in `module load frameworks`; **`hdf5/1.14.6` is a separate module and is
   required** (frameworks' h5py links `libhdf5.so.310`, absent from the default
   path, so `import h5py` fails outright); and `swift/venv`
   (`--system-site-packages`) supplies swift's own deps.
2. **HDF5 2.0 vs 1.14 -- this one nearly cost a queued job.** The pilot was
   written with `libver="latest"` under swift_env's HDF5 **2.0.0**, producing
   superblock 3, which frameworks' HDF5 **1.14.6 cannot read**. Keys list fine;
   every read then raises `bad version number for layout message`. Fixed in
   `nnja_grid_pilot.py` (default libver, which HDF5 2.0 still writes
   1.14-readably); `h5_downgrade.py` rewrote all 2922 files in place, verified.
   It detects the old format from the **superblock byte**, not by attempting a
   read -- the only library that can read these files is the one that cannot
   tell them apart. **Run it with swift_env's python, not the venv's.**
3. **Importing a model inits MPI**, which aborts on a login node
   (`Fatal error in internal_Init_thread`). Anything touching `swift.models` or
   `swift.train` has to go through `qsub`; `aurora-obs-check.sh` exists for that.

### sigma_data was wrong by 3x

`sigma_data` is the **actual data scale** in the SCM schedule
(`t = atan(tau/sigma_data)`, `z = randn * sigma_data`), not a free knob. Because
89.1% of every plane is imputed to exactly zero, the standardized fields are far
smaller than ERA5's. Measured over 120 train windows:

```
standardized + imputed INPUT   std = 0.410
standardized RESIDUAL TARGET   std = 0.311
over observed cells only       std = 1.240 / 0.983   (correctly ~unit)
```

The ERA5 configs use `sigma_data: 1.0`; the obs experiment sets **0.31** in both
`loss` and `precond`. Leaving it at 1.0 does not error -- it silently
mis-calibrates the entire noise schedule. Note the **solver** takes `sigma_data`
from the net, not its own config (`generating/diffusion.py:305`), so it must not
be set there; hydra would reject the key.

### Verification ladder

Ordered so the silent failures are caught before a long run. `trainer.py:225`
runs `torch.nan_to_num(param.grad, nan=0)`, so a NaN loss yields a *completed*
run with a NaN log and zero parameter change -- it must be asserted, not
eyeballed.

| rung | status |
| --- | --- |
| 1. stats sane, match independent measurement | **pass** |
| 2. dataset: shapes, finite, imputation, round-trip | **pass** |
| 2b. same, with the TOA forcing channel | **pass** |
| 3. loss finite; grads finite AND nonzero *before* `nan_to_num` | queued (`aurora-obs-check.sh`) |
| 4. parameters actually move | queued |
| 5. one-batch overfit | pending |
| 6. baselines measured (persistence **and** diurnal climatology) | **pass** |

Note rungs 3-5 must run through `qsub`: importing any `swift.models` module
initializes MPI, which aborts on a login node with
`Fatal error in internal_Init_thread`. `aurora-obs-check.sh` exists for this.
A first attempt also failed on the test harness rather than the code --
`PassPrecond` builds its model from a hydra `model_config`, it does not accept a
model instance.

Rung 2 results: 0 non-finite across sampled windows, unobserved cells exactly
zero, observed cells standardize to std 1.00-1.33, round-trip error 9.5e-07,
`w_obs` mean exactly 1.0.

Rung 2b, with the forcing: `cond_ch=5 / target_ch=4`, `x` (5,128,256) and `t`
(4,128,256), 0 non-finite over 30 windows. **`w_obs` comes back (1,4,128,256) --
sized to the TARGET channels, not the condition channels**; at 5 it would
broadcast-mismatch the 4-channel residual. The per-channel standardized spread
also confirms the `sigma_data` correction directly:

```
2m_temperature        all-cell std 0.485   observed-cell std 1.287
10m_u                 all-cell std 0.366   observed-cell std 1.096
toa_incident_solar    all-cell std 1.045   (dense, so no dilution)
```

The observation channels sit near 0.4 because ~89% is imputed zero; only the
computed forcing is near 1.

**Test-split baselines (6h, observed cells, latitude-weighted).** The
climatology is fitted on train and applied to test:

| variable | persistence | **+diurnal clim** | fill | also in input |
| --- | --- | --- | --- | --- |
| `2m_temperature` | 4.414 K | **2.849 K** (-35%) | 11.29% | 95.6% |
| `10m_u_component_of_wind` | 2.049 m/s | **1.977** (-3.5%) | 11.15% | 95.6% |
| `10m_v_component_of_wind` | 2.135 m/s | **2.082** (-2.5%) | 11.15% | 95.6% |
| `mean_sea_level_pressure` | 474.9 Pa | **456.9** (-3.8%) | 10.15% | 96.1% |

**The diurnal-climatology column is the bar**, not persistence. A 2t model
landing at 3.5 K would look like a 21% win over persistence while being 23%
*worse* than a lookup table that knows only the clock.

Two readings worth keeping. The diurnal effect is **almost entirely
temperature** -- 2t falls 35%, wind and pressure only 2-4%, because solar
heating drives near-surface temperature directly while synoptic wind/pressure
changes are not phase-locked to the clock; so the TOA forcing should help 2t
substantially and the rest marginally. And the out-of-sample number is weaker
than in-sample (35% on December against 47% on the train split), which is the
honest direction for a seasonal mismatch.

(December msl exceeds the annual 351.8 Pa -- winter storms.)

### The diurnal cycle is 47% of the 6h signal -- and the baseline was too weak

Measured on the train split before running anything. The 6h 2t increment is
dominated by time of day:

```
00->06  mean +1.886 K      12->18  mean -1.020 K
06->12  mean +0.102 K      18->00  mean -0.456 K

persistence                        RMSE = 4.614 K
persistence + diurnal climatology  RMSE = 2.441 K   (-47.1%)
```

The second baseline is a per-cell, per-transition mean increment: it knows the
analysis hour and **nothing else** -- no dynamics, no weather. It nearly halves
the error. Two consequences:

1. **Persistence alone is not the bar.** A model beating 4.41 K could still be
   worse than a lookup table. `eval_masked.py` now reports both, fitting the
   climatology on train and applying it to test.
2. **The model could not reach this at all** with `forcings: []` -- the only
   time-of-day cue was which stations happened to report. A null result would
   have been uninterpretable: "cannot learn from observations" versus "we
   withheld half the signal".

### TOA solar forcing (added, `work/nnja/make_toa.py`)

Pure solar geometry, so it is computed rather than downloaded: Spencer (1971)
declination series, NOAA equation of time, Earth-Sun distance correction,
10-minute midpoint quadrature. Verified **before** writing any data:

```
area-weighted global-mean flux = 340.3 W/m2   vs theoretical S0/4 = 340.2  (0.02%)
Jun solstice max 1317 W/m2 at lat +23.2   (expect ~+23.4)
Dec solstice max 1408 W/m2 at lat -23.2
night fraction 50.0%
```

**The convention matters and is not the obvious one.** A first version
accumulated over the 6-hour step and came out 6x larger than ERA5's `tisr`
normalize_mean. The factor was 6.83, not 6 -- so it was not a step-length error.
Working back from ERA5's 1.0766e6 implies a **1-hour** accumulation, and the
1-hour value here is 1.0738e6: a 0.3% match. **WeatherBench2 `tisr` is
J/m^2 accumulated over the ONE hour ending at the analysis time.** Scaling to
fit instead of checking would have put the channel on the wrong scale silently.

Written to all 1461 windows with a `__cnt` plane of ones (so it reads through
the same path as observed variables and is never treated as missing). Train-split
statistics come out at mean 1.059e6 / fill 100%, against ERA5's 1.077e6.

Note `_transform_standardize` (era5.py:124-128) dispatches on **channel count**:
with 4 variables + 1 forcing, 5 matches neither 4 nor 1 so the full stats array
is used -- correct, but it would silently pick the wrong normalization if the
counts ever collided.

### The training budget is 3% of the paper's -- read early results accordingly

The Swift paper trains **15,000 kimg with a 3,000 kimg tangent warmup**
(`era5-swinv2-1.4-scm.yaml`). The observation config is scaled to what a 1-hour
debug job allows:

| setting | paper | obs | ratio |
| --- | --- | --- | --- |
| `total_kimg` | 15000 | 500 | **3.3%** |
| `tangent_warmup_kimg` | 3000 | 300 | 10% |
| `lr_rampup_kimg` | 2000 | 50 | 2.5% |
| `ema_halflife_kimg` | 500 | 50 | 10% |

The data gap is the sharper one. The paper sees ~58,000 distinct ERA5 states;
we have **1,214 windows**. So 500 kimg is ~412 epochs against the paper's ~258
-- *more* passes over **48x fewer distinct samples**. Whatever this run shows,
it is not a test of the same thing the paper tested.

At the measured ~8.2 s/kimg, matching the paper's 15 mimg would take ~34 hours
= ~34 chained debug jobs; even reaching the 3 mimg warmup alone is ~7 jobs.

**Consequence for interpretation:** a flat or worse-than-baseline result at 500
kimg is weak evidence about whether Swift can learn from observations. It is
consistent with (a) genuinely no signal, (b) nowhere near enough training, and
(c) nowhere near enough distinct data -- and these numbers cannot separate them.
Before concluding anything, either extend the chain substantially or build more
years (2011+), which addresses the data gap rather than only the step count.

### If this run fails: extend to 2010-2020, surface only

Decided 2026-09-22. The data gap (48x) is far larger than the step-count gap
(3x), so more distinct samples is the higher-leverage fix -- and it is cheap.
**Verified: `conv/adpsfc/NC000001` has all 4018 days of 2010-2020, no gaps**,
17.4 GB of raw parquet.

| | 2010 only | 2010-2020 |
| --- | --- | --- |
| windows | 1,214 train | **16,072** (13x) |
| gridded size | 0.187 GB | **~2.1 GB** |
| build time | ~7 min | **~1.3 h**, streamed, raw discarded |
| 500 kimg = | 412 epochs | 31 epochs |
| paper-equivalent 258 epochs | 15 kimg (!) | **~4,150 kimg** |

That last row is the point: on one year, 500 kimg is already 412 epochs -- far
past the paper's 258 -- so the model has seen its data to death without ever
seeing much. On eleven years the same budget is 31 epochs, which is
under-trained but *honest*, and ~4,150 kimg would match the paper's ratio.

Build it with:

```bash
python nnja_grid_pilot.py --start 2011-01-01 --end 2020-12-31 \
    --datasets adpsfc --out grids
python make_toa.py --root grids --source adpsfc      # forcing for the new years
python make_splits.py                                 # re-split chronologically
python make_norm_stats.py --variables 2m_temperature,\
10m_u_component_of_wind,10m_v_component_of_wind,mean_sea_level_pressure,\
toa_incident_solar_radiation --intervals 6
```

All four scripts skip existing output, so 2010 is not rebuilt. Two things to
get right: **`make_splits.py` hardcodes the 2010 date ranges** and must be
updated (e.g. train 2010-2018, val 2019, test 2020) -- a random split would
leak, since neighbouring 6h windows are strongly correlated; and stats must be
**recomputed**, since the current ones are fitted on ten months of 2010.

Surface only, deliberately: `conv/adpupa` (upper air) starts 2010 too, but at
~0.93% fill per level it is below anything published, and adding it would
confound "more data" with "much harder target".

### Derived fields must be rebuilt when the grids are extended

Cost two jobs on 2026-09-23. The 11-year build ran `make_toa.py` while only 2010
existed, then added 2011-2020 -- so the new years had no solar forcing. The run
died instantiating the *validation* dataset:

```
ValueError: variables not present in any source under .../swift_root_11y/val:
            ['toa_incident_solar_radiation']
```

The nasty part is that **train worked**. `_resolve_sources` reads the first file
of each split, and train's first file is from 2010, which *does* have TOA. Only
val (2019) and test (2020) failed. Had the split boundaries fallen differently,
training could have started on an inconsistent dataset instead of erroring.

Two rules follow, and the build order in this file already implied both:

1. **TOA (and any derived field) is rebuilt after every grid extension**, not
   once. `make_toa.py` is idempotent -- it skips windows that already have the
   field -- so re-running it is cheap and always correct.
2. **Statistics must be recomputed too.** Fitting TOA on 2010 alone while the
   field spans eleven years mis-scales the channel silently; unlike the missing
   field, nothing raises.

`/tmp/finish11y.sh` encodes the check that would have caught this: sample the
first, middle and last window of **all three splits**, not just whichever one
happens to contain the original year.

### Other expected difficulties, recorded before the run
- **1214 training windows** against 500 kimg is ~400 epochs; expect the val
  curve, not the final number, to be the result.
- **95.6% input/target mask overlap at 6h** makes copying the input a strong
  strategy. If test RMSE lands at persistence, that is what happened; SOLID's
  overlap reweighting (lambda 0.05-0.1) is the countermeasure.
- **Off-network predictions will relax to climatology** -- GraphDOP reports
  exactly this. Measure it rather than be surprised by it.
- `w_obs` makes the loss value incomparable to ERA5 runs. Do not read across.

## Session end 2026-09-23: where things stand

### Headline: Swift DOES learn from sparse observations

The 1-year pilot beat both baselines on the variables the loss weights.
Scored with `eval_masked.py` (single 6h step, observed cells only, the same
metric as the baselines), `checkpoint-000433`:

| variable | model | persistence | diurnal clim | vs diurnal |
| --- | --- | --- | --- | --- |
| `2m_temperature` | **2.617 K** | 4.414 | 2.849 | **-8.1%** |
| `mean_sea_level_pressure` | **381.0 Pa** | 474.9 | 456.9 | **-16.6%** |
| `10m_u_component_of_wind` | 2.144 m/s | 2.049 | 1.977 | +8.4% |
| `10m_v_component_of_wind` | 2.245 m/s | 2.135 | 2.082 | +7.8% |

The collapse diagnostic is healthy: between-input variation is 40-46% of the
spatial std, so the output tracks its input rather than being a constant field.

Wind loses, which is expected -- `_calculate_variable_weights` gives 10u/10v a
weight of 0.1 against 2t's 1.0, so the loss barely optimises them.

### The mistake that cost the most time

I spent several exchanges concluding the pilot had "flat validation, no
learning" from Swift's built-in `val/rmse` (5.146 at init, 5.148 at 352 kimg).
**That metric is autoregressive over three lead times and averages over every
grid cell, including the ~89% never observed** -- which is precisely why
`eval_masked.py` exists. Reasoning from it led to killing a healthy training
chain on a false divergence diagnosis, and nearly to abandoning the approach.

Two corollaries worth keeping:

- **The SCM training loss is not a fit metric.** It rises with the noise
  schedule; a rising loss is not divergence. The lr 0.02 -> 0.008 change was
  made on that false premise (it is better justified on batch-scaling grounds,
  but it fixed nothing -- 4x lower LR reproduced the same curve exactly).
- **Always score with `eval_masked.py`** before drawing any conclusion.

### Run in flight

```
8859250  PARTID=0  RUNNING   results/obs-nnja-11y-swinv2-1.4-scm/000
8859273  PARTID=1  HELD      afterany:8859250
```

11-year data, 2 of a possible 8 jobs, ~800 of 3397 kimg. Validation so far
(**in-training metric, NOT comparable to the table above**):

```
kimg     2t      u      v     msl
   0  5.403  2.049  2.054   448.9
  25  5.335  2.022  2.047   501.0   <- msl spike
  50  5.394  2.081  2.104   432.3
  75  5.284  2.153  2.192   408.2
 100  5.250  2.082  2.100   383.0
 126  5.185  2.077  2.101   335.3
```

msl falls 449 -> 335 (-25%) and 2t 5.40 -> 5.19 (-4%). Encouraging, and a
different shape from the pilot (which oscillated with no direction) -- but note
the kimg=25 msl **spike to 501**, so this is not strictly monotonic and four or
five points is not a trend. The LR ramp runs to 453 kimg, so at kimg 126 the
model is at ~28% of full LR and still in the regime where anything improves.

**Two jobs may not be enough.** The schedule is calibrated for the full 3397
kimg (ramp 453 = 13% of training, matching the paper); at 800 kimg the ramp is
57% of the run. If the curve is ambiguous when the chain ends, extend to 8 jobs
rather than re-tuning.

### Next steps, in order

1. When `8859273` finishes, score its last checkpoint:
   ```
   module load frameworks hdf5/1.14.6
   source /lus/flare/projects/Swift-Reanalysis/swift/venv/bin/activate
   python work/nnja/eval_masked.py --split test --delta 6 \
       --experiment obs-nnja-11y-swinv2-1.4-scm \
       --checkpoint <results/obs-nnja-11y-.../001/checkpoints/checkpoint-*.pt>
   ```
   Compare against **2.617 K / 381.0 Pa** (the pilot), not the baselines.
   NOTE: the 11y test split is 2020, the pilot's was Dec 2010 -- so the
   baselines must be recomputed on the new split before comparing.
2. Extend the chain if the answer is ambiguous:
   `SCRIPT=aurora-obs.sh bash scripts/chain-resume.sh -s 2 -n 6 -b 4 -e obs-nnja-11y-swinv2-1.4-scm`
   (submit one at a time -- `debug` allows ONE queued job per user)
3. If wind still loses, try raising its `w_var` weight above 0.1 -- that is the
   most likely cause, not the data.

### Infrastructure notes

- Branch `swift_obs` on `rcjackson/swift`, pushed. No file overlap with the
  earlier `obs_only` branch (different design: obs condition an ERA5 target).
- `swift_root` = 2010 pilot; `swift_root_11y` = 2010-2020. Both intact.
- `results/.../000-lr0.02-diverged` is the original 1-year run, kept as the
  comparison curve.
- Four separate API-drift failures cost a queue cycle each: `ezpz.setup_torch`
  dropped `backend=`, IPEX 2.10 moved the memory helpers to `torch.xpu`,
  `PassPrecond` takes `model_config` not a model, and hydra needs
  `_recursive_=False` there. `aurora-obs.sh` now preflights the first two.
- `debug` is the only usable queue (prod/small/medium need >=256 nodes), 1h cap,
  ONE queued job per user.

## Still open

Items 1-6 belong to the **AIFS-DOP path**; they only matter if that pipeline is
revived (e.g. to recover the pre-1998 record NNJA lacks).

1. ~~**ATMS is three years short**~~ — **settled by NNJA**, whose ATMS runs
   2012-02-15 to 2025-03-31.
2. **Upper-air coverage gap.** CUON is radiosonde/pilot-balloon only. Table 1
   also lists **aircraft** and **AMV**, which CUON does not contain — those
   still need a separate source. *(NNJA has the same gap: `conv/adpupa` is
   rawinsonde. NNJA does carry `conv/adpsfc NC000007` METAR/aviation, not yet
   evaluated.)*
3. **GridSat `irwvp` is absent before ~1985**, so a full-period build carries an
   all-NaN channel in the early years. Decide: tolerate, start the WV record
   later, or split into two datasets with different date ranges.
4. **Confirm 11 (`ts`) is really SST** vs. 12 (`tsts`), if you later use ODB.
5. **The `csv:` source cannot read parquet** — blocks the AIFS-DOP scaled
   output. Moot for NNJA, which bypasses anemoi entirely and writes h5 directly.
6. **Report the `group_by` indexing bug upstream** (or patch locally) so a
   40-year ODB build does not need one query per analysis time.

Live items for the **current path**:

7. **How Swift ingests observation grids — the real blocker.** `ERA5Dataset`
   reads dense per-timestep HDF5 and indexes neighbours by **integer file
   offset**, assuming a gapless 6-hourly sequence of complete fields. Gridding
   fixes the *shape* (128 x 256 float32, Swift's variable names) but leaves:
   - **the sparse-input problem**, which is the hard one: the 69 are input as
     well as target, so a ~1%-filled level is a nearly empty state to
     autoregress from. Decide how the model is conditioned on a partial state —
     `__cnt` as extra input channels, a mask in the loss, some infilling, or a
     different formulation entirely.
   - **missing windows must be tolerated** (see the 4 real AMSU-A gaps), so
     integer-offset indexing must become timestamp lookup;
   - normalization statistics computed **over observed cells only** — the ERA5
     `normalize_mean.npz` / `normalize_std.npz` do not transfer, and
     `_load_and_stack` expects that exact npz layout.
8. **Retarget the gridder at CUON + CDS surface.** Swap the `build` functions
   for the wide-CSV sources; windowing, accumulation and writing are unchanged.
9. **Extend the CUON and CDS surface recipes to start 1979.** CUON itself covers
   1901-2024, so this is a date change; confirm the CDS surface collections
   reach 1979 too.
10. **Quality control.** Conventional obs carry raw outliers (NNJA adpsfc `2t`
    spanned 173.6-372.5 K, 0.0088% implausible, nearly all `__cnt == 1`).
    Stratospheric `q` above ~200 hPa is at the radiosonde detection limit and is
    effectively noise. Choose a `__cnt` threshold and physical-range clip.
11. **Aircraft and AMV are still missing** from CUON (was item 2) — a density
    gap in the upper air, not a variable gap.

## Progress

- [x] Read the observation recipes and the tabular/ODB machinery
- [x] Installed anemoi-datasets, codc/pyodc, and the `odc` CLI
- [x] Confirmed no real ODB data exists on this filesystem
- [x] Wrote `make_synthetic_odb.py` to unblock pipeline testing
- [x] Found and fixed 3 blocking bugs (window syntax, group_by data loss, statid)
- [x] All 10 recipes build and pivot correctly against synthetic data
- [x] Verified every varno against the official ECMWF table; fixed msl
      (110 → 108) and added the missing sst (11)
- [x] Cross-checked all periods/citations against Table 1 — all match
- [x] Resolved HIRS and SSM/T-2 to EUMETSAT collection ids; confirmed coverage
      and that search is public / download needs OAuth2
- [x] Installed cdsapi + credentials; wired surface (marine + land), upper-air,
      GridSat and AMSU-A to **real open data**; validated all physically
- [x] Established the long→wide pivot path (the `csv:` source cannot pivot)
- [x] Wired AMSU-B, MHS and MSU to the AWS Open Data FCDR buckets — all with
      their complete channel sets
- [x] Located ATMS on the EUMETSAT Data Store (`EO:EUM:DAT:0345`); ruled out the
      AWS and NCEI alternatives
- [x] Registered EUMETSAT credentials; downloaded and wired HIRS, SSM/T-2 and
      ATMS — **all 10 Table 1 datasets now build from real data**
- [x] Closed the AMSU-A channel gap with the NESDIS gridded FCDR (channels
      4–14), built as a companion dataset; rewrote `combine.yaml` to match
- [ ] *(AIFS-DOP)* Report the `group_by` indexing bug upstream (or patch
      locally) so a 40-year build does not need one query per analysis time

### NNJA gridding work

- [x] Explored `gs://gcp-nnja-ai`; confirmed anonymous public access works from
      the login node, mapped all 14 datasets and their real date ranges
- [x] Established that NNJA ships **already-pivoted** wide parquet, removing the
      whole `*_to_wide.py` converter layer
- [x] Measured grid coverage at 1.4°: AMSU-A 97.0% / MHS 88.6% per 6h window —
      the finding that makes a dense gridded encoding viable
- [x] Wrote `nnja_grid_pilot.py`: stream GCS parquet → 1.40625° grids → h5,
      raw discarded, resumable; verified the WB2 lat/lon convention
- [x] Found and fixed the **00Z window bug** (~69% loss, silent); rebuilt
- [x] Added `__cnt` sparsity planes and `__min`/`__max` for radiances
      (recovers 1.5× the deep-convection cells)
- [x] Measured storage: **22× smaller** gridded than raw; ~0.3 TB full period
- [x] Added dewpoint → specific humidity (Bolton 1980) and 600 hPa log-p
      interpolation — **all 69 Swift variables now produced**, verified against
      `swift.data.constants.VARS`
- [x] 2010 pilot: adpsfc, adpupa, AMSU-A complete and validated
- [x] Established that Swift's 69 variables are **input as well as target**, so
      radiances have no slot in the architecture — **decided option 3: train on
      state variables only**, which makes CUON + CDS surface the better source
- [ ] Retarget `nnja_grid_pilot.py` at the CUON / CDS surface wide CSVs
- [ ] Extend the CUON + CDS surface recipes to 1979
- [ ] **Build the Swift-side ingest path** (open item 7) — the real blocker,
      now centred on how a sparse state is used as *input*
- [x] Deleted the 2010 radiance grids (~6.9 GB) and removed `amsua`/`mhs` from
      the builder — first evaluation is state variables only. Surviving output:
      `grids/adpsfc` + `grids/adpupa`, 1461/1461 windows each, 709 MB, 69/69 vars
- [-] ATMS 2010+ — dropped with radiances
- [ ] Recompute normalization statistics over observed cells
- [ ] Full-period builds + train/val/test split
