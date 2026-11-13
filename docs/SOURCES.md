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

### JPL Horizons sample (independent check)

File `data/raw/horizons_sample.txt` (not committed, 14662 bytes, retrieved 2026-11-13 19:09 UTC):
two responses of the Horizons API (version 1.2), Sun first, then Earth.

Endpoint: `https://ssd.jpl.nasa.gov/api/horizons.api` (documentation:
https://ssd-api.jpl.nasa.gov/doc/horizons.html). Parameters:

```
format=text  COMMAND='10' (Sun) or '399' (Earth)  OBJ_DATA='NO'  MAKE_EPHEM='YES'
EPHEM_TYPE='OBSERVER'  CENTER='coord@301'  COORD_TYPE='GEODETIC'
SITE_COORD='222.5104,-89.4632,1.9448'   (east longitude deg, latitude deg, height km)
START_TIME='2027-01-01 00:00'  STOP_TIME='2027-01-02 00:00'  STEP_SIZE='1 h'
QUANTITIES='4'  APPARENT='AIRLESS'  ANG_FORMAT='DEG'  CSV_FORMAT='YES'
```

The site is the centre of the Site01 (Connecting ridge) 5 m raster with its DEM height; it is
a test point, not a landing site. What the response header states: ephemeris source DE441;
centre frame "MEAN_ME (high precision)"; centre radii 1737.4 km (sphere), so the height is
measured above the same sphere as the LOLA heights; no refraction. Output columns are
apparent azimuth and elevation of the target centre in degrees, 25 hourly rows per target.
First row (2027-01-01 00:00 UTC): Sun azimuth 40.612702, elevation 1.421435; Earth azimuth
144.641343, elevation -6.686183.

### SPICE kernels (local calculation)

All from the NAIF generic kernels archive, https://naif.jpl.nasa.gov/pub/naif/generic_kernels/,
downloaded 2026-11-13 to `data/raw/kernels/` (not committed). All load in spiceypy 8.4.0
(CSPICE N0067); both SPK files also open in skyfield 1.55.

| File | Path under generic_kernels/ | Size (bytes) | Content | SHA-256 |
|---|---|---|---|---|
| `de440s.bsp` | spk/planets/ | 32726016 | Planetary ephemeris DE440 (short span); Moon coverage 1849-12-26 to 2150-01-21 | `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2` |
| `de421.bsp` | spk/planets/a_old_versions/ | 16790528 | Planetary ephemeris DE421; Moon coverage 1899-07-29 to 2053-10-08 | `08b20db2ae22488650641c5a9033e5bfda4b1c4b440cfeaf20f621cfa18ecdb3` |
| `moon_pa_de440_200625.bpc` | pck/ | 12863488 | Lunar orientation, principal-axis frame of DE440 (frame 31008), 1549-12-31 to 2650-01-24 | `60cd55aa401ea2ea97360636f567554bfe4e37bb829f901b4460a455dfaf783f` |
| `moon_pa_de421_1900-2050.bpc` | pck/ | 1770496 | Lunar orientation, principal-axis frame of DE421 (frame 31006), 1900-01-01 to 2050-12-31 | `656f90616403d75a75f0cd6c8830fc5b44f8cb4facb5ccb8915e752b397520cf` |
| `moon_de440_250416.tf` | fk/satellites/ | 19478 | Frame kernel: MOON_PA_DE440, MOON_ME_DE440_ME421 | `a47c71e9c9f33796bdafb2c9d69a7ee447b6016ecad80f71cd6f3e479f9cf768` |
| `moon_080317.tf` | fk/satellites/ | 21437 | Frame kernel: MOON_PA_DE421, MOON_ME_DE421 | `78732477b96f9863e7b0d65bcee3c22b8707ca5ed0db56d1173319cb2e8c7993` |
| `pck00011.tpc` | pck/ | 131226 | Body radii and IAU orientation constants | `3dff7b1dbeceaa01f25467767d3fa25816051c85d162d1edf04acb310ee28bb1` |
| `naif0012.tls` | lsk/ | 5257 | Leap seconds | `678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b` |

Two complete sets are available: DE421 (`de421.bsp` + `moon_pa_de421_1900-2050.bpc` +
`moon_080317.tf`, frame `MOON_ME_DE421`, the frame of the LOLA terrain) and DE440
(`de440s.bsp` + `moon_pa_de440_200625.bpc` + `moon_de440_250416.tf`, frame
`MOON_ME_DE440_ME421`). Which set the ephemeris module uses is decided in T05.

## Landing sites

_To be filled in T04: source of every site coordinate._

## Published values used for validation

_To be filled in T05 and T07._

## Development tooling (not part of the solution)

| Component | Source | Version | Retrieved (UTC) | Notes |
|---|---|---|---|---|
| `.claude/agents/python-reviewer.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | Code-review agent for Claude Code, copied unchanged |
| `.claude/skills/python-testing/SKILL.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | pytest guidance for Claude Code, copied unchanged |
