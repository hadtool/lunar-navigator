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
model is used for the far horizon and the 5 m site models for the near field.

### Terrain north of 80 S (check only) - PGDA product 90

| File | URL | Size (bytes) | Server Last-Modified | Downloaded (UTC) | SHA-256 |
|---|---|---|---|---|---|
| `LDEM_60S_240MPP_ADJ.TIF` | https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_60S_240MPP_ADJ.TIF | 218961039 | 2023-07-07 | 2026-11-13 | `3f9663257b63022f2b0d5a623482ff3cadddceb91594a4e4ca14a94d8cec8b34` |

Properties read from the file: 7760 x 7760 pixels, 240 m/pixel, extent X and Y from -931200
to +931200 m (60-90 S), same projection, float32, no nodata pixels, height range -9127.1 to
+7024.8 m. Agreement with the 40 m model at 20000 random points inside the 40 m extent:
mean difference 0.05 m, standard deviation 3.0 m.

This file is not used to produce results. It was used once (T19) to test whether terrain
outside the 40 m model can rise above the horizon of our sites; it cannot, see assumption A5
in docs/ASSUMPTIONS.md. `pipeline/build_horizons.py --with-240m` adds it as a third layer if
a site farther from the pole is ever added.

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
| `Site04_final_adj_5mpp_surf.tif` | Site04: Shackleton rim | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site04/Site04_final_adj_5mpp_surf.tif | 40980806 | 2020-06-05 | 2026-11-13 | `38ff70dbdf2f066c2cfa94a646c3a59d653ce7f6b4528b15fc1b43ee397ce758` |
| `Site07_final_adj_5mpp_surf.tif` | Site07: Peak near Shackleton | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site07/Site07_final_adj_5mpp_surf.tif | 40980808 | 2020-06-05 | 2026-11-13 | `38aaee10bb4da4d63e7427aa1ca25c79bdbc649d212079a04990e135462091f8` |
| `Site11_final_adj_5mpp_surf.tif` | Site11: de Gerlache rim | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site11/Site11_final_adj_5mpp_surf.tif | 40980806 | 2020-06-05 | 2026-11-13 | `58f3372c35bbd6baf38ffd5633c1c96b59bd89dbd252150581d12893a43136e5` |
| `Site06_final_adj_5mpp_surf.tif` | Site06: Nobile rim 1 | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site06/Site06_final_adj_5mpp_surf.tif | 64025603 | 2021-02-12 | 2026-11-13 | `cca17e8067601dd659b583f889204db6bce685bc30c60a9e62427a8bce36b03d` |
| `Site20v2_final_adj_5mpp_surf.tif` | Site20v2: Leibnitz beta plateau (v2) | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site20v2/Site20v2_final_adj_5mpp_surf.tif | 108192905 | 2022-08-03 | 2026-11-13 | `0e96c40987c0814eadd4f94f85dacbb33bcab5388dd0b1dc99dc59bf987f072f` |
| `Haworth_final_adj_5mpp_surf.tif` | Haworth | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Haworth/Haworth_final_adj_5mpp_surf.tif | 142123767 | 2020-11-25 | 2026-11-13 | `387fd6e99bca266f4982f7256c4c185921105313882b4c2eee5b5ff1ef75016b` |

Properties read from the files (5 m/pixel, plain uncompressed GeoTIFF, no overviews, no nodata pixels):

| File | Pixels | Extent X (m) | Extent Y (m) | Centre (lat, east lon) | Height range (m) |
|---|---|---|---|---|---|
| `Site01_final_adj_5mpp_surf.tif` | 3200 x 3200 (16 x 16 km) | -19000 .. -3000 | -20000 .. -4000 | -89.4632, 222.5104 | -523.2 .. 1959.5 |
| `Site23_final_adj_5mpp_surf.tif` | 4200 x 4200 (21 x 21 km) | -11000 .. 10000 | 111000 .. 132000 | -85.9948, 359.7642 | 902.0 .. 5173.6 |
| `DM2_final_adj_5mpp_surf.tif` | 4000 x 4000 (20 x 20 km) | 147000 .. 167000 | 85000 .. 105000 | -83.9540, 58.8221 | -1430.0 .. 1817.6 |
| `Site04_final_adj_5mpp_surf.tif` | 3200 x 3200 (16.0 x 16.0 km) | -9000 .. 7000 | -15000 .. 1000 | -89.7668, 188.1301 | -2847.9 .. 1805.1 |
| `Site07_final_adj_5mpp_surf.tif` | 3200 x 3200 (16.0 x 16.0 km) | 22000 .. 38000 | -28000 .. -12000 | -88.8110, 123.6901 | -418.9 .. 1648.7 |
| `Site11_final_adj_5mpp_surf.tif` | 3200 x 3200 (16.0 x 16.0 km) | -45000 .. -29000 | 7000 .. 23000 | -88.6834, 292.0679 | -805.2 .. 1816.0 |
| `Site06_final_adj_5mpp_surf.tif` | 4000 x 4000 (20.0 x 20.0 km) | 74000 .. 94000 | 100000 .. 120000 | -85.4381, 37.3667 | 859.6 .. 6800.1 |
| `Site20v2_final_adj_5mpp_surf.tif` | 5200 x 5200 (26.0 x 26.0 km) | 60000 .. 86000 | 105000 .. 131000 | -85.4266, 31.7428 | 1330.2 .. 6787.7 |
| `Haworth_final_adj_5mpp_surf.tif` | 5960 x 5960 (29.8 x 29.8 km) | -52900 .. -23100 | 75600 .. 105400 | -86.7639, 337.2230 | -1642.9 .. 2842.2 |

The centre coordinates are the centres of the rasters, computed with pyproj from the file
CRS; they are not landing-site coordinates.

Other 5 m site models available in the same product and not downloaded: Site20 (older
version of Leibnitz beta plateau), Site42, Shoemaker, DM1, LM1-LM8, NPA-NPD, SL2, SL3.

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

Site list: `data/sites.json` (committed). All coordinates are planetocentric latitude and east
longitude in the mean Earth / polar axis (ME) system; pages retrieved 2026-11-13.

| Sites | Coordinate source | Precision |
|---|---|---|
| Twelve polar candidates (table below) | A specific candidate landing site from the open dataset of Wueller et al. (2026), see below | Specific point proposed in a study; not NASA-selected |
| Shackleton Rim, Leibnitz Beta Plateau | Centre of the PGDA 5 m raster (Site04, Site20v2), computed with pyproj from the raster bounds. Site names from https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README. No matching region in the Wueller dataset | Approximate: region centre, not a landing point |
| IM-2 Athena | LROC featured image "IM-2 Athena Seen Obliquely", https://www.lroc.asu.edu/images/1408: lander at 84.7906 S, 29.1957 E. (Intended site per https://www.lroc.asu.edu/images/1401: -84.78, 29.13 E.) The LROC page does not state the frame explicitly; ME is assumed. | Located in images |
| Apollo 11 Lunar Module | NSSDC "Lunar Landing Sites", https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html: 0.67416 N, 23.47314 E, ME/polar axis system, DE421, after Wagner et al., 2017, Icarus 283, 92-103 | Located in images |

Artemis III candidate regions. The latest official list found is the nine regions announced
on 28 October 2024: Peak near Cabeus B, Haworth, Malapert Massif, Mons Mouton Plateau, Mons
Mouton, Nobile Rim 1, Nobile Rim 2, de Gerlache Rim 2, Slater Plain. Source: George et al.,
"Artemis III Site Selection Update: Downselection From Thirteen to Nine Candidate Regions",
LPSC 2026 abstract, https://ntrs.nasa.gov/citations/20250011660, which cites the NASA news
release of 28 Oct 2024. Neither document gives coordinates of the regions. Four of the nine
have a PGDA 5 m raster of the same name. None of the official documents gives a landing point.

Site coordinates therefore come from a peer-reviewed open dataset, not from NASA:
Wueller et al., 2026, "Complementary Data for Wueller et al. (2026): Assessing Potential
Landing Sites with Favorable Illumination and Accessible, Potentially Volatile-Rich
Permanently Shadowed Regions within Artemis Candidate Landing Regions", Zenodo,
https://doi.org/10.5281/zenodo.17084058 (CC BY 4.0; paper: JGR Planets 131(3), e2025JE009434,
https://doi.org/10.1029/2025JE009434). File `Landing_Sites.zip` (11852963 bytes, retrieved
2026-11-13), shapefile `LandingSites`: 130 candidate landing sites in 16 regions, attributes
`Landing_Re` (region code), `Name`, `Latitude`, `Longitude`, and per-year counts of sunlit
days (`SunDays25` .. `Sundays32`) and of days with Sun and Earth (`SunEarth..`).

Selection rule (decided with the team on 2026-11-13): for each region, take the site with
the most sunlit days in the Wueller model summed over 2027-2029 (our analysis window); ties
are broken by the most Sun-and-Earth days over the same years, then by the lowest site ID.
This deliberately picks well-lit points, so the list is not a neutral sample of each region.
Several sites share the same counts (31, 17, 18), which looks like the full length of the
modelled window; how the counts are defined must be read in the paper before they are used
for validation.

| Site in `sites.json` | Wueller site | Sites in region | Lat, east lon | Sunlit days 2027, 2028, 2029 (Wueller) | PGDA 5 m raster containing the point | Shift from the previous region centre |
|---|---|---|---|---|---|---|
| Connecting Ridge | CR06 | 9 | -89.4441, 222.7090 | 31, 18, 18 | Site01 | 0.6 km |
| Peak near Shackleton | 007 | 6 | -88.8113, 123.5540 | 31, 17, 18 | Site07 | 0.1 km |
| de Gerlache Rim | 011 | 6 | -88.6744, 291.7720 | 31, 17, 18 | Site11 | 0.3 km |
| Malapert Massif | MMA_K2023 | 5 | -85.9919, 2.0564 | 31, 17, 18 | Site23 | 4.9 km |
| Haworth | HW06 | 11 | -87.0499, 335.7598 | 30, 17, 18 | Haworth | 9.0 km |
| Nobile Rim 1 | NR101 | 9 | -85.2950, 36.9168 | 31, 17, 18 | Site06 | 4.5 km |
| Nobile Rim 2 | NR205 | 9 | -83.6185, 59.0568 | 3, 20, 12 | DM2 | 10.2 km |
| Peak near Cabeus B | PCB02 | 5 | -83.6317, 292.3661 | 8, 13, 13 | none | 5.2 km |
| Mons Mouton Plateau | MMP04 | 11 | -84.6863, 20.8866 | 8, 14, 15 | none | 28.2 km |
| Mons Mouton | MMO01 | 10 | -85.4160, 31.8506 | 31, 17, 18 | Site20v2 | 1.7 km |
| de Gerlache Rim 2 | dGR2_K2023 | 7 | -88.4500, 292.1409 | 20, 17, 17 | Site11 | 8.4 km |
| Slater Plain | SP06 | 11 | -87.0730, 126.1310 | 20, 9, 10 | none | 4.1 km |

The mapping of PGDA site names to Wueller region codes (CR, PNS, dGR1, MMA, HW, NR1, NR2) is
ours, by name. The shapefile CRS is a south polar stereographic projection on the 1737.4 km
sphere ("GCS_Moon", D_Moon_2000); it does not name the ME or PA system, ME is assumed. The
Mons Mouton site lies inside the PGDA Leibnitz Beta Plateau raster: both entries describe the
same massif. Nobile Rim 2 (NR205) is close to the edge of the DM2 raster, so the 5 m model
covers its surroundings only partly.

### Wueller et al. (2026) illumination rasters (T22, definition only)

`Illumination_Modeling.zip` from the same Zenodo record (https://zenodo.org/records/17084058/files/Illumination_Modeling.zip,
10731432 bytes, SHA-256 `5596caddff12fc70e19df89af69fbafa83350a7b191d71ddada743862ce17c60`, retrieved 2026-11-14, stored in `data/raw/wueller2026_illumination/`, not
committed). It holds a nested archive of GeoTIFFs per region and year (`<Region>_MaxConsecDaysOfSun_Midsummer<YYYY>GT`
and `..._MaxConsecDaysOfSun+Earth_...`), an ArcGIS layer file and `READ_ME.txt`, which states: "The illumination
shows the number of consecutive 12-hour time increments in the model. Therefore, to derive the number of
consecutive illuminated days, the value must be divided by two. The values in the attribute tables have already
been divided and indicate the number of consecutive illuminated days."

So `SunDays25`..`Sundays32` of the landing-site table are the **largest number of consecutive days with sunlight
within the "midsummer" window of each year**, sampled every 12 hours, and `SunEarth..` the same for Sun and Earth
together. Not stated in the dataset: the dates of the midsummer windows, the illumination threshold (any part of
the disc or more), the observer height and the terrain model. The paper (doi:10.1029/2025JE009434) could not be
opened from our tools (publisher 403, repository refused the connection), so no comparison with our results has
been made.

Update 2026-11-15: the paper was provided by the team (PDF downloaded by the programmer from the
publisher, stored as `data/raw/papers/wueller2026_jgr_planets.pdf`, 6379927 bytes, SHA-256
`5c948e494847abf245e6765731f50593f8b7f31e2eb1de127f240685b4db786c`, not committed). Section 2.3 gives
the method (QuickMap TerrainShadows, 60 m/pixel, 12 h steps, observer 2 m above the surface, shadows
up to 150 km, a step counts when non-zero), Table 2 the midsummer windows (sub-solar latitude <= -1.5
deg) and Table A2 the values per site; the comparison is in docs/VALIDATION.md (T22).

## LROC imagery (visual check of horizons, T06)

LROC WAC south-polar summer mosaic, 64 pixels/degree browse GeoTIFF (8 bit):
https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/WAC_ROI/WAC_ROI_SOUTH_SUMMER/WAC_ROI_SOUTH_SUMMER_064P.TIF
(36967887 bytes, SHA-256 `f368c1d315fe49616dd7f0d52856c1520ed0a1677ee4d1f450ba1c60a13b1330`, retrieved 2026-11-14, stored in `data/raw/lroc_wac/`, not committed). 6076 x 6076
pixels of 473.8 m, south polar stereographic projection with the same parameters as the LOLA models (lat_0 -90,
lon_0 0, sphere 1737.4 km). Product description (README of the product): WAC 643 nm images taken between 2010-09-21
and 2010-10-23, when the sub-solar point was near its southernmost latitude, mosaicked to minimise shadows.
Reference: Speyerer, E. J., Robinson, M. S., Boyd, A., Wagner, R. V., Henriksen, M. R. (2020), Exploration of the
lunar south pole with LROC data products, Lunar Surface Science Workshop, abstract 5132. This is the WAC imagery LROC
QuickMap displays; the QuickMap web interface itself was not used. Used only by `pipeline/check_horizon_wac.py`.

## Published values used for validation

### Ephemeris module (T05)

Horizons reference tables: `tests/data/horizons_<site>_<sun|earth>.txt` (committed, unmodified
API responses, retrieved 2026-11-13 by `pipeline/fetch_horizons_reference.py`). Same endpoint
and settings as the sample query above, with `QUANTITIES='4,13,20'` (azimuth and elevation,
angular diameter, range) and `TIME_DIGITS='SECONDS'`.

| Site | SITE_COORD (east lon deg, lat deg, height km) | Times (UTC) |
|---|---|---|
| connecting_ridge (Wueller CR06) | 222.7090, -89.4441, 1.9557 | 2027-01-01 00:00 to 2029-11-01, step 45 d, 24 rows |
| malapert_massif (Wueller MMA_K2023) | 2.0564, -85.9919, 5.1694 | 2027-01-01 06:00 to 2029-11-01, step 45 d, 24 rows |
| apollo_11 (Lunar Module) | 23.47314, 0.67416, 0 | 1969-07-20 20:17:40 and 20:18:40 |

Heights of the two polar sites are LOLA heights read from `LDEM_80S_40MPP_ADJ.TIF`.

Result of the comparison (our SPICE calculation minus Horizons, largest angular separation):
Sun 0.000001 deg and Earth 0.000026 deg at both polar sites; Apollo 11: Sun 0.0002 deg,
Earth 0.00003 deg. The task limit is 0.01 deg.

Apollo 11 published value: NASA SP-4029 "Apollo by the Numbers", Apollo 11 summary,
https://www.nasa.gov/wp-content/uploads/static/history/SP-4029/Apollo_11a_Summary.htm :
"The planned launch window for Apollo 11 extended to 17:54:00 GMT to take advantage of a sun
elevation angle on the lunar surface of 10.8 deg", and the landing time 20:17:39 GMT on
20 July 1969. This is the planned Sun elevation, not a measurement at touchdown. Our result
for 20:17:40 UTC at the Lunar Module position, height 0: Sun elevation 10.7035 deg, azimuth
88.8055 deg (Horizons: 10.7033, 88.8055).

Body radii for angular sizes: `pck00011.tpc` (Sun 695700 km, Earth equatorial 6378.1366 km).

### Illumination and Earth visibility (T07)

Published maps of the LOLA team, method of Mazarico et al. (2011, Icarus 211, 1066-1081,
doi:10.1016/j.icarus.2010.10.030), release 2016-08. Product page:
https://pgda.gsfc.nasa.gov/products/69 (PGDA "Lunar Polar Illumination"); PDS originals and
labels: http://imbrium.mit.edu/EXTRAS/ILLUMINATION/ . Stored in `data/raw/illumination/`
(not committed), used only by `pipeline/validate_illumination.py`.

| File | URL | Size (bytes) | Server Last-Modified | Downloaded (UTC) | SHA-256 |
|---|---|---|---|---|---|
| `AVGVISIB_85S_060M_201608.TIF` | https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_85S_060M_201608.TIF | 33994464 | 2025-03-20 | 2026-11-14 | `ccf67d4f39e0a970c111196da7d6551ffcf50d075470b93067fb3904c0b05806` |
| `AVGVISIB_85S_060M_201608_EARTH.TIF` | https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_85S_060M_201608_EARTH.TIF | 24862958 | not recorded | 2026-11-14 | `d71dc5adfff653e0e924e0a4cbf03795b996caa30b4ace3d5843a70a5ab2f3d2` |

Properties read from the files: 5058 x 5058 pixels, 60 m/pixel, extent X and Y from -151740
to +151740 m, the same south polar stereographic projection as the terrain, int16 with scale
factor 0.00004 (value = DN x 0.00004, between 0 and 1). The PDS label
(`AVGVISIB_85S_060M_201608.LBL`) gives the frame "MEAN EARTH/POLAR AXIS OF DE421" and the
definition: the values "indicate the percentage of timesteps where each pixel was sunlit (by
any fraction of the solar disc)", computed on the elevation map `LDEM_85S_060M`. The product
page states that the maps are averages "over hourly timesteps spanning 18.6 years" and that
for the Earth map "the Earth is considered visible if any part of its disc is not obscured".
The start date of the 18.6 years is not given on the page or in the label. Largest value in
the solar map: 0.884.

The `_COG.TIF` links on the product page returned an HTML page instead of a file on
2026-11-14, so the plain GeoTIFFs were downloaded. The comparison and its result are in
docs/VALIDATION.md.

### Physical constants of the power model (T08)

| Constant | Value | Source |
|---|---|---|
| Total solar irradiance at 1 au | 1361 W/m2 | IAU 2015 Resolution B3, nominal total solar irradiance; measured value 1360.8 +- 0.5 W/m2 at solar minimum in Kopp & Lean (2011), Geophys. Res. Lett. 38, L01706, doi:10.1029/2010GL045777 |
| Astronomical unit | 149597870700 m | IAU 2012 Resolution B2 (exact by definition) |

The Sun-site distance comes from the ephemeris module, so the irradiance follows the
Earth-Moon system around its orbit: over 2027-2029 the distance at Connecting Ridge is
0.9807 to 1.0193 au (our calculation), which changes the power by +4.0 % to -3.8 %.

### Default lander values (proposed, T23 and engineering inputs)

Stored in `data/raw/papers/` (not committed), retrieved 2026-11-14; the values are entered in
docs/ENGINEERING_INPUTS.md with the mark [предложено] (not confirmed by the engineer, A14).

| Document | URL | Size (bytes) | SHA-256 | Values taken |
|---|---|---|---|---|
| NASA GRC COMPASS team, "Overnight Power & Thermal Solutions for Lunar Landers", Survive the Night Technology Workshop, 2022 (NTRS 20220018215) | https://ntrs.nasa.gov/citations/20220018215 | 11883330 | `da6c1c46bca7c7779f03660ad5453ea2e78c628a9f0fd503843f0065f8446ef3` | "Night-time power reqt's ~ 40W", "EPS losses total ~6W" (night load 46 W); "~20 kWh capacity" Li-ion battery of LG 18650 MJ1 cells; "Use 90% DoD"; "Specific energy of ~200 Whr/kg" |
| Spectrolab, XTJ Prime space solar cell datasheet (2016) | https://www.spectrolab.com/DataSheets/cells/XTJ_Prime_Data_Sheet_7-28-2016.pdf | 434537 | `a3b08e1042526a5d3e42b7c879942317c303fa390d48372d226b1f4e83d7b737` | 30.7 % efficiency at the beginning of life (AM0, 28 C, production average) |
| NASA Small Spacecraft Systems Virtual Institute, State-of-the-Art of Small Spacecraft Technology, 2024 edition | https://www.nasa.gov/smallsat-institute/sst-soa/ | 18337707 | `7471ed49b8cce48c0d0da7662e979017a6a6720d9fecb0adc52f120a123adeae` | Table 9-3: IRIS V2.2 transponder, Tx 8400-8500 MHz, 36 dBm (3.98 W), 0.1-10000 kbps; Table 9-2: EnduroSat X-band patch array, 16 dBi, flight heritage (T24) |

Textbook and standard values used in the T24 sizing (`pipeline/size_power_and_link.py`; not
downloaded, quoted from the reference works):

| Reference | Value taken |
|---|---|
| Wertz, J. R., Larson, W. J. (eds.), Space Mission Analysis and Design, 3rd ed., 1999, Sec. 11.4 | Eq. 11-5 (array power from day and night loads with path efficiencies X_d = 0.80, X_e = 0.60 for peak-power tracking); Table 11-35 inherent degradation I_d = 0.77 (nominal) |
| ITU-R Recommendation P.526 (propagation by diffraction) | Knife-edge diffraction loss of about 6 dB at grazing incidence (v = 0) |
| CCSDS 130.1-G (TM synchronization and channel coding, summary of concept and rationale) | Rate-1/2, K = 7 convolutional code with Viterbi decoding: Eb/N0 about 4.4 dB for BER 1e-5 |

## Precomputed data for the app (T12)

One command rebuilds everything the app reads, from the raw terrain and the SPICE kernels:
`uv run python pipeline/build.py` (`--skip-horizons` reuses the cached horizons). The app reads
these files through `lunarnav.store` and needs neither `data/raw/` nor the kernels.

| File in `data/processed/` | Content | Size |
|---|---|---|
| `horizons/<site>_h<height>.json` | Terrain horizon, 720 azimuths, for the 15 polar sites and the mast heights of docs/ENGINEERING_INPUTS.md (placeholder 0, 2, 5, 10, 20 m), 75 files | 1.3 MB |
| `ephemeris/centre_ephemeris_hourly.parquet` | Apparent Sun and Earth vectors from the Moon's centre in the ME frame (light time and aberration, as in `lunarnav.ephemeris`), float64, hourly from 2027-01-01 to 2030-02-01 UTC (27 048 steps; one month beyond 2029 so that a mission landing late in 2029 fits) | 1.9 MB |
| `metrics/visibility_metrics.json` | Sun, Earth-link and Sun-and-Earth shares, longest night and longest Earth gap per site, height and period (2027-2029 and each year), 300 rows | 54 KB |
| `manifest.json` | Build command, timings, inputs (heights, link rule, kernels, terrain), software versions, size and SHA-256 of every file | - |

The hourly azimuth and elevation of the Sun and the Earth are not stored per site: the app
derives them from the stored vectors with `ephemeris.sky_track` (pure numpy, a few
milliseconds per site), the same code the pipeline uses, so there is one source of truth.

Measured on 2026-11-14 (laptop, 12 CPU threads, one process), two full builds: 94.3 s and
101.9 s, of which horizons 86.5 s and 94.2 s (loading the 40 m model plus 2.4 to 7.0 s per
site), ephemeris 0.8 to 0.9 s, metrics 6.9 s; with `--skip-horizons` 9.3 s. Total size of
`data/processed/` after the build: 3.3 MB (87 files), well inside the 50 MB budget for the
deployed app; the build stops with an error above the budget. The manifest records the size and
SHA-256 of the five kernels and of the ten terrain files used (the 40 m model and nine 5 m
models), so a rebuild can be traced to its inputs. Checks: the rebuilt horizons are byte-for-byte identical to the
committed ones; the stored ephemeris equals a fresh SPICE run exactly at sampled times
(`tests/test_store.py`); in a copy of the repository without `data/raw/` the app chain
(visibility, three years of power, mast trade-off, calendar of 1096 landings) runs in 1.0 s for
one site and gives the same numbers as T10 and T11.

## Development tooling (not part of the solution)

| Component | Source | Version | Retrieved (UTC) | Notes |
|---|---|---|---|---|
| `.claude/agents/python-reviewer.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | Code-review agent for Claude Code, copied unchanged |
| `.claude/skills/python-testing/SKILL.md` | https://github.com/affaan-m/ECC | commit d2ef268 (2026-11-06), MIT | 2026-11-13 | pytest guidance for Claude Code, copied unchanged |
