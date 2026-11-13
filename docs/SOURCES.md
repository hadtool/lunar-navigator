# Sources

Every external dataset, kernel, API and published value used by the project is listed here:
exact file name, URL, size, download date (UTC) and how it is used. Large files live in
`data/raw/` and are not committed.

## Challenge resources (official)

| Resource | URL | Used for |
|---|---|---|
| Challenge page | https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/ | Problem statement |
| JPL Horizons | https://ssd.jpl.nasa.gov/horizons/ (API: https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Independent check of Sun/Earth azimuth and elevation |
| LROC Quickmap | https://quickmap.lroc.asu.edu/ | Visual check of terrain, screenshots |
| Moon Trek | https://trek.nasa.gov/moon/ | 3D terrain view |
| CSA Moon Exploration | https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/ | Mission context |

## Terrain (LOLA, NASA PGDA)

All terrain files are LOLA (Lunar Orbiter Laser Altimeter, LRO) elevation models from the
NASA GSFC Planetary Geodesy Data Archive (PGDA). They are stored in `data/raw/lola/` and are
not committed. Pixel values are surface heights in metres above the 1737.4 km reference sphere.

Common georeferencing (read from the files with rasterio 1.5.2 / GDAL 3.12.2 and confirmed by
the product pages): south polar stereographic projection, `+proj=stere +lat_0=-90 +lon_0=0
+x_0=0 +y_0=0 +R=1737400 +units=m`, X/Y in metres, MOON_ME (mean Earth / polar axis) frame
of the JPL DE421 ephemeris. With this projection `x = r*sin(lon)`, `y = r*cos(lon)`:
+Y points to longitude 0 E, +X to 90 E. Data type float32, nodata = NaN.

### Regional model (far horizon) - PGDA product 90

Product page: https://pgda.gsfc.nasa.gov/products/90 ("A New View of the Lunar South Pole from LOLA").
Citation required by the data usage policy: Barker et al., 2023, Planet. Sci. J., 4, 183,
https://doi.org/10.3847/PSJ/acf3e1 (data DOI 10.60903/gsfcpgda-lola-spole).

| File | URL | Size (bytes) | Server Last-Modified | Downloaded (UTC) | SHA-256 |
|---|---|---|---|---|---|
| `LDEM_80S_40MPP_ADJ.TIF` | https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_40MPP_ADJ.TIF | 716299920 | 2023-07-07 | 2026-11-13 | `b7f3567bfa405dbcb42f867f6cd3c9932ca9752b4363ce1eef835f9115c1dd76` |

Properties read from the file: 15200 x 15200 pixels, 40 m/pixel, extent X and Y from
-304000 to +304000 m (a square centred on the pole; the middle of each edge is at about
80 S), Cloud-Optimized GeoTIFF with 512 x 512 deflate-compressed tiles and overviews
2, 4, 8, 16, 32. CRS name in the file: "Moon (2015) - Sphere / Ocentric / South Polar"
(IAU:30135). Height range documented in the file tag `z#actual_range`: -7296.5 to +7026.8 m.
Height next to the pole (mean of the four pixels sharing the corner at x = y = 0): 1289.4 m.

Access decision: the file is downloaded in full. It can also be read window by window over
HTTP (`/vsicurl/`, tested: open 1.1 s, 3 x 3 pixel read 1.0 s), which remains the fallback,
but horizon calculation reads long profiles around every site and local reads are faster and
do not depend on the network during the hackathon.

Not downloaded: `LDEM_80S_20MPP_ADJ.TIF` (20 m/pixel, 2.6 GB per the product page). The 40 m
model is used for the far horizon and the 5 m site models for the near field. The same
product also offers `LDEM_60S_240MPP_ADJ.TIF` (60-90 S, 240 m/pixel, 210 MB per the product
page) for terrain beyond 80 S; whether it is needed is tracked as a separate task.

### Site models (near horizon) - PGDA product 78

Product page: https://pgda.gsfc.nasa.gov/products/78 ("South Pole Landing Site LOLA DEMs"),
README: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README. Reference: Barker et al., 2021,
Planetary and Space Science, 203, 105119, https://doi.org/10.1016/j.pss.2020.105119.
Site numbering follows Mazarico et al., 2011, Icarus, 211, 1066-1081,
https://doi.org/10.1016/j.icarus.2010.10.030. Per the README, X/Y are pixel centres in the
GMT "pixel-registered" convention and `*_surf.tif` is the surface height with interpolation
filling empty pixels.

| File | Site (README name) | URL | Size (bytes) | Server Last-Modified | Downloaded (UTC) | SHA-256 |
|---|---|---|---|---|---|---|
| `Site01_final_adj_5mpp_surf.tif` | Site01: Connecting ridge | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_surf.tif | 40980810 | 2020-06-05 | 2026-11-13 | `3ba7b97cb00a2bcf21189c3aeb535f65afc21207154ab9f0d43c5bdc1f7e747e` |
| `Site23_final_adj_5mpp_surf.tif` | Site23: Malapert massif | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site23/Site23_final_adj_5mpp_surf.tif | 70586804 | 2020-06-12 | 2026-11-13 | `12d280a59cd7580415f6bada638d0abe025ce6727541fddf68d5dc371a6c94cf` |
| `DM2_final_adj_5mpp_surf.tif` | DM2: Nobile rim 2 | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/DM2/DM2_final_adj_5mpp_surf.tif | 64025607 | 2021-02-08 | 2026-11-13 | `d88677c21633683061117db0a577f0510e0948fe9db315d13be28782407ff604` |

Properties read from the files (5 m/pixel, plain uncompressed GeoTIFF, no overviews, no nodata pixels):

| File | Pixels | Extent X (m) | Extent Y (m) | Centre (lat, east lon) | Height range (m) |
|---|---|---|---|---|---|
| `Site01_final_adj_5mpp_surf.tif` | 3200 x 3200 (16 x 16 km) | -19000 .. -3000 | -20000 .. -4000 | -89.4632, 222.5104 | -523.2 .. 1959.5 |
| `Site23_final_adj_5mpp_surf.tif` | 4200 x 4200 (21 x 21 km) | -11000 .. 10000 | 111000 .. 132000 | -85.9948, 359.7642 | 902.0 .. 5173.6 |
| `DM2_final_adj_5mpp_surf.tif` | 4000 x 4000 (20 x 20 km) | 147000 .. 167000 | 85000 .. 105000 | -83.9540, 58.8221 | -1430.0 .. 1817.6 |

The centre coordinates are the centres of the rasters, computed with pyproj from the file
CRS; they are not landing-site coordinates.

Other 5 m site models available in the same product and not downloaded yet (surface files of
41-142 MB each): Site04 (Shackleton rim), Site06 (Nobile rim 1), Site07 (Peak near
Shackleton), Site11 (de Gerlache rim), Site20 and Site20v2 (Leibnitz beta plateau), Site42,
Haworth, Shoemaker, DM1, LM1-LM8, NPA-NPD, SL2, SL3.

## Ephemerides and kernels

_To be filled in T03: Horizons sample query, planetary ephemeris, lunar orientation kernels._

## Landing sites

_To be filled in T04: source of every site coordinate._

## Published values used for validation

_To be filled in T05 and T07._

## Development tooling (not part of the solution)

| Component | Source | Version | Retrieved (UTC) | Notes |
|---|---|---|---|---|
| `.claude/agents/python-reviewer.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | Code-review agent for Claude Code, copied unchanged |
| `.claude/skills/python-testing/SKILL.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | pytest guidance for Claude Code, copied unchanged |
