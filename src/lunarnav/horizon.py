"""Terrain horizon of a lunar south-polar site.

For an observer standing ``mast_height_m`` above the surface, the horizon profile gives,
for each azimuth, the largest elevation angle of any terrain point along that direction.
The Sun or the Earth is hidden when it is below this angle.

Method
------
The Moon is a sphere of radius R = 1737.4 km carrying the LOLA heights. A terrain point
at great-circle distance ``d`` (central angle ``psi = d / R``) and height ``z`` is seen
from an observer at radius ``r_o`` under the elevation angle::

    elevation = atan2(r_p * cos(psi) - r_o, r_p * sin(psi)),   r_p = R + z

which is the exact form of ``arcsin((P - O) . n / |P - O|)`` for 3-D vectors ``P`` (terrain
point), ``O`` (observer) and local vertical ``n``. Curvature is therefore exact; nothing
is linearised.

Rays are sampled with a radial step of one pixel of the finest terrain model near the
site, growing proportionally to distance farther out. Each azimuth bin is covered by
several sub-rays and reports the maximum, so a peak between two bin centres is picked up
by the bin it lies in. The sampling is finite, so this is not a strict upper bound; the
measured sampling error is below 0.002 deg on the sites tested (docs/ASSUMPTIONS.md, A9).

Terrain models are tried from finest to coarsest: a 5 m site model near the site, the
40 m regional model beyond it and, outside 80 S, the 240 m model. Angles are radians,
lengths metres, azimuth is clockwise from north (see ``lunarnav.ephemeris``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import ArrayLike, NDArray

from lunarnav.ephemeris import MOON_RADIUS_M, local_axes

DEFAULT_AZIMUTH_COUNT = 720
DEFAULT_MAX_RANGE_M = 300_000.0
DEFAULT_SUBRAYS = 4
#: Radial step as a fraction of distance once it exceeds the finest pixel size.
DEFAULT_STEP_GROWTH = 0.001
_AZIMUTH_CHUNK = 256


class Terrain(Protocol):
    """A height model in south polar stereographic coordinates."""

    name: str
    pixel_m: float

    def sample(self, x_m: NDArray[np.float64], y_m: NDArray[np.float64]) -> NDArray[np.float64]:
        """Heights (m above the reference sphere) at the points; NaN where there is no data."""
        ...


def south_polar_xy(
    unit_vectors: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Project ME-frame unit vectors to south polar stereographic X/Y (metres).

    Same projection as the LOLA rasters: ``+proj=stere +lat_0=-90 +lon_0=0 +R=1737400``,
    true scale at the pole, +Y towards longitude 0 and +X towards 90 E.
    """
    scale = 2.0 * MOON_RADIUS_M / (1.0 - unit_vectors[..., 2])
    return scale * unit_vectors[..., 1], scale * unit_vectors[..., 0]


def lat_lon_to_xy(lat_rad: float, lon_east_rad: float) -> tuple[float, float]:
    """South polar stereographic X/Y of a point given by latitude and east longitude."""
    unit = np.array(
        [
            np.cos(lat_rad) * np.cos(lon_east_rad),
            np.cos(lat_rad) * np.sin(lon_east_rad),
            np.sin(lat_rad),
        ]
    )
    x, y = south_polar_xy(unit)
    return float(x), float(y)


class RasterTerrain:
    """North-up raster of heights with square pixels, sampled bilinearly."""

    def __init__(
        self,
        heights_m: NDArray[np.floating],
        x_left_m: float,
        y_top_m: float,
        pixel_m: float,
        name: str = "raster",
    ) -> None:
        if heights_m.ndim != 2:
            raise ValueError("heights_m must be a 2-D array")
        if pixel_m <= 0:
            raise ValueError("pixel_m must be positive")
        self.heights_m = heights_m
        self.x_left_m = float(x_left_m)
        self.y_top_m = float(y_top_m)
        self.pixel_m = float(pixel_m)
        self.name = name

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        bounds_m: tuple[float, float, float, float] | None = None,
    ) -> RasterTerrain:
        """Read a GeoTIFF; ``bounds_m`` = (left, bottom, right, top) limits what is loaded."""
        import rasterio
        from rasterio.windows import Window

        path = Path(path)
        with rasterio.open(path) as dataset:
            transform = dataset.transform
            if not (transform.b == 0 and transform.d == 0 and np.isclose(transform.a, -transform.e)):
                raise ValueError(f"{path.name}: expected a north-up raster with square pixels")
            projection = dataset.crs.to_dict() if dataset.crs else {}
            radius = projection.get("R", projection.get("a"))
            if not (
                projection.get("proj") == "stere"
                and projection.get("lat_0") == -90
                and projection.get("lon_0", 0) == 0
                and radius == MOON_RADIUS_M
                # True scale at the pole, no false origin, metres: south_polar_xy assumes it.
                and projection.get("lat_ts", -90) == -90
                and projection.get("k_0", projection.get("k", 1)) == 1
                and projection.get("x_0", 0) == 0
                and projection.get("y_0", 0) == 0
                and projection.get("units", "m") == "m"
                and dataset.scales[0] == 1.0
                and dataset.offsets[0] == 0.0
            ):
                raise ValueError(
                    f"{path.name}: expected south polar stereographic on the 1737.4 km sphere, "
                    f"got {projection}"
                )
            pixel = float(transform.a)
            col_off, row_off, width, height = 0, 0, dataset.width, dataset.height
            if bounds_m is not None:
                left, bottom, right, top = bounds_m
                col_off = max(0, int(np.floor((left - transform.c) / pixel)))
                row_off = max(0, int(np.floor((transform.f - top) / pixel)))
                col_end = min(dataset.width, int(np.ceil((right - transform.c) / pixel)))
                row_end = min(dataset.height, int(np.ceil((transform.f - bottom) / pixel)))
                width, height = col_end - col_off, row_end - row_off
                if width <= 0 or height <= 0:
                    raise ValueError(f"{path.name}: requested bounds do not overlap the raster")
            heights = dataset.read(1, window=Window(col_off, row_off, width, height))
            if dataset.nodata is not None and not np.isnan(dataset.nodata):
                heights = np.where(heights == dataset.nodata, np.nan, heights)
        return cls(
            heights,
            x_left_m=transform.c + col_off * pixel,
            y_top_m=transform.f - row_off * pixel,
            pixel_m=pixel,
            name=path.name,
        )

    @property
    def bounds_m(self) -> tuple[float, float, float, float]:
        """(left, bottom, right, top) of the pixel edges."""
        rows, cols = self.heights_m.shape
        return (
            self.x_left_m,
            self.y_top_m - rows * self.pixel_m,
            self.x_left_m + cols * self.pixel_m,
            self.y_top_m,
        )

    def sample(self, x_m: NDArray[np.float64], y_m: NDArray[np.float64]) -> NDArray[np.float64]:
        """Bilinear interpolation between pixel centres.

        Points inside the raster but within half a pixel of its edge take the value of
        the edge pixels (no extrapolation). A NaN pixel makes the result NaN only where
        it has a non-zero interpolation weight. Points outside the raster give NaN.
        """
        x_m = np.asarray(x_m, dtype=np.float64)
        y_m = np.asarray(y_m, dtype=np.float64)
        n_rows, n_cols = self.heights_m.shape
        # Pixel centres sit at half-integer pixel offsets from the raster edge.
        cols = (x_m - self.x_left_m) / self.pixel_m - 0.5
        rows = (self.y_top_m - y_m) / self.pixel_m - 0.5
        inside = (cols >= -0.5) & (cols <= n_cols - 0.5) & (rows >= -0.5) & (rows <= n_rows - 0.5)
        out = np.full(x_m.shape, np.nan)
        if not inside.any():
            return out
        col = np.clip(cols[inside], 0.0, n_cols - 1.0)
        row = np.clip(rows[inside], 0.0, n_rows - 1.0)
        col0 = np.minimum(col.astype(np.intp), max(n_cols - 2, 0))
        row0 = np.minimum(row.astype(np.intp), max(n_rows - 2, 0))
        col1 = np.minimum(col0 + 1, n_cols - 1)
        row1 = np.minimum(row0 + 1, n_rows - 1)
        wx = col - col0
        wy = row - row0
        value = np.zeros(col.shape)
        for row_index, col_index, weight in (
            (row0, col0, (1.0 - wy) * (1.0 - wx)),
            (row0, col1, (1.0 - wy) * wx),
            (row1, col0, wy * (1.0 - wx)),
            (row1, col1, wy * wx),
        ):
            used = weight > 0.0
            # Zero-weight neighbours are skipped so that their NaN cannot leak in.
            value[used] += weight[used] * self.heights_m[row_index[used], col_index[used]]
        out[inside] = value
        return out


class FunctionTerrain:
    """Analytic height model ``z = f(x, y)``, used for synthetic tests."""

    def __init__(
        self,
        function: Callable[[NDArray[np.float64], NDArray[np.float64]], ArrayLike],
        pixel_m: float,
        name: str = "function",
    ) -> None:
        self._function = function
        self.pixel_m = float(pixel_m)
        self.name = name

    def sample(self, x_m: NDArray[np.float64], y_m: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray(self._function(np.asarray(x_m), np.asarray(y_m)), dtype=np.float64)


def sample_terrains(
    terrains: Sequence[Terrain], x_m: NDArray[np.float64], y_m: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Heights from the first terrain (finest first) that has data at each point."""
    heights = np.full(np.shape(x_m), np.nan)
    for terrain in terrains:
        missing = np.isnan(heights)
        if not missing.any():
            break
        heights[missing] = terrain.sample(x_m[missing], y_m[missing])
    return heights


def ray_distances(
    first_step_m: float,
    max_range_m: float,
    growth: float = DEFAULT_STEP_GROWTH,
) -> NDArray[np.float64]:
    """Sample distances along a ray: constant step near the site, then proportional to distance."""
    if first_step_m <= 0 or max_range_m <= first_step_m:
        raise ValueError("need 0 < first_step_m < max_range_m")
    if growth <= 0:
        raise ValueError("growth must be positive")
    switch = first_step_m / growth
    linear = np.arange(first_step_m, min(switch, max_range_m) + 0.5 * first_step_m, first_step_m)
    if linear[-1] >= max_range_m:
        return linear[linear <= max_range_m]
    count = int(np.ceil(np.log(max_range_m / linear[-1]) / np.log1p(growth)))
    geometric = linear[-1] * (1.0 + growth) ** np.arange(1, count + 1)
    return np.concatenate([linear, np.minimum(geometric, max_range_m)])


@dataclass(frozen=True, eq=False)
class HorizonProfile:
    """Terrain horizon seen from one observer position.

    ``azimuth_rad[k]`` is the centre of bin ``k``; the bin spans half a step to either
    side and ``elevation_rad[k]`` is the highest terrain elevation found inside it.
    ``distance_m[k]`` is the distance of the terrain point that defines the horizon and
    ``covered_range_m[k]`` the distance up to which terrain data is continuous along the
    bin (the first gap ends it, even if data resumes farther out).
    """

    lat_rad: float
    lon_east_rad: float
    ground_height_m: float
    mast_height_m: float
    max_range_m: float
    azimuth_rad: NDArray[np.float64]
    elevation_rad: NDArray[np.float64]
    distance_m: NDArray[np.float64]
    covered_range_m: NDArray[np.float64]
    terrain_names: tuple[str, ...] = ()

    def elevation_at(
        self, azimuth_rad: ArrayLike, *, interpolate: bool = False
    ) -> NDArray[np.float64]:
        """Horizon elevation at arbitrary azimuths (array in, array out; scalar gives 0-d).

        By default the value of the bin that contains the azimuth is returned, which is
        what the bins mean (maximum over the bin). ``interpolate=True`` interpolates
        linearly between bin centres instead; that is smoother but reads a peak that
        fills one bin at half height near the bin edges.
        """
        azimuth = np.mod(np.asarray(azimuth_rad, dtype=np.float64), 2.0 * np.pi)
        if interpolate:
            return np.interp(azimuth, self.azimuth_rad, self.elevation_rad, period=2.0 * np.pi)
        count = self.azimuth_rad.size
        index = np.floor(azimuth / (2.0 * np.pi / count) + 0.5).astype(np.intp) % count
        return self.elevation_rad[index]

    def to_dict(self) -> dict:
        """JSON-ready representation; angles in degrees for readability."""
        return {
            "units": {"angles": "deg", "lengths": "m", "azimuth": "clockwise from north"},
            "lat_deg": float(np.rad2deg(self.lat_rad)),
            "lon_east_deg": float(np.rad2deg(self.lon_east_rad)),
            "ground_height_m": round(self.ground_height_m, 2),
            "mast_height_m": self.mast_height_m,
            "max_range_m": self.max_range_m,
            "terrain_names": list(self.terrain_names),
            "azimuth_step_deg": 360.0 / self.azimuth_rad.size,
            "elevation_deg": np.round(np.rad2deg(self.elevation_rad), 5).tolist(),
            "distance_m": np.round(self.distance_m, 0).tolist(),
            "covered_range_m": np.round(self.covered_range_m, 0).tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> HorizonProfile:
        elevation = np.deg2rad(np.asarray(data["elevation_deg"], dtype=np.float64))
        azimuth = np.arange(elevation.size) * (2.0 * np.pi / elevation.size)
        return cls(
            lat_rad=float(np.deg2rad(data["lat_deg"])),
            lon_east_rad=float(np.deg2rad(data["lon_east_deg"])),
            ground_height_m=float(data["ground_height_m"]),
            mast_height_m=float(data["mast_height_m"]),
            max_range_m=float(data["max_range_m"]),
            azimuth_rad=azimuth,
            elevation_rad=elevation,
            distance_m=np.asarray(data["distance_m"], dtype=np.float64),
            covered_range_m=np.asarray(data["covered_range_m"], dtype=np.float64),
            terrain_names=tuple(data.get("terrain_names", ())),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> HorizonProfile:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def cache_path(directory: str | Path, site_id: str, mast_height_m: float) -> Path:
    """``<directory>/<site>_h<height>.json``, e.g. ``connecting_ridge_h2.json``."""
    return Path(directory) / f"{site_id}_h{mast_height_m:g}.json"


def horizon_profile(
    lat_rad: float,
    lon_east_rad: float,
    mast_height_m: float,
    terrains: Sequence[Terrain],
    *,
    azimuth_count: int = DEFAULT_AZIMUTH_COUNT,
    max_range_m: float = DEFAULT_MAX_RANGE_M,
    subrays: int = DEFAULT_SUBRAYS,
    step_growth: float = DEFAULT_STEP_GROWTH,
) -> HorizonProfile:
    """Terrain horizon for one observer height; see :func:`horizon_profiles`."""
    return horizon_profiles(
        lat_rad,
        lon_east_rad,
        [mast_height_m],
        terrains,
        azimuth_count=azimuth_count,
        max_range_m=max_range_m,
        subrays=subrays,
        step_growth=step_growth,
    )[0]


def horizon_profiles(
    lat_rad: float,
    lon_east_rad: float,
    mast_heights_m: Sequence[float],
    terrains: Sequence[Terrain],
    *,
    azimuth_count: int = DEFAULT_AZIMUTH_COUNT,
    max_range_m: float = DEFAULT_MAX_RANGE_M,
    subrays: int = DEFAULT_SUBRAYS,
    step_growth: float = DEFAULT_STEP_GROWTH,
) -> list[HorizonProfile]:
    """Terrain horizons for observers at several heights above the same surface point.

    The terrain along the rays is sampled once and reused for every height.

    Parameters
    ----------
    lat_rad, lon_east_rad:
        Site position (ME frame). Only the southern hemisphere is supported because the
        terrain is in south polar stereographic coordinates.
    mast_heights_m:
        Heights of the observer (solar panel, antenna) above the local surface, each >= 0.
    terrains:
        Height models ordered from finest to coarsest. The surface height at the site is
        taken from the first one that covers it.
    azimuth_count, subrays:
        Number of azimuth bins and of rays traced inside each bin (maximum is kept).
    max_range_m:
        Length of the rays.
    """
    heights_m = [float(height) for height in mast_heights_m]
    if not terrains:
        raise ValueError("at least one terrain model is required")
    if not heights_m:
        raise ValueError("at least one mast height is required")
    if lat_rad >= 0:
        raise ValueError("only southern-hemisphere sites are supported")
    if min(heights_m) < 0:
        raise ValueError("mast heights must be >= 0")
    if azimuth_count < 4 or subrays < 1:
        raise ValueError("azimuth_count must be >= 4 and subrays >= 1")

    east, north, up = local_axes(lat_rad, lon_east_rad)
    site_x, site_y = south_polar_xy(up)
    site_xy = (np.array([float(site_x)]), np.array([float(site_y)]))
    ground_height = float(sample_terrains(terrains, *site_xy)[0])
    if np.isnan(ground_height):
        raise ValueError("no terrain data at the site")
    first_step = next(
        terrain.pixel_m for terrain in terrains if not np.isnan(terrain.sample(*site_xy)[0])
    )
    observer_radii = [MOON_RADIUS_M + ground_height + height for height in heights_m]

    distances = ray_distances(first_step, max_range_m, step_growth)
    psi = distances / MOON_RADIUS_M
    cos_psi, sin_psi = np.cos(psi), np.sin(psi)
    # 1 - cos(psi), computed without cancellation for the first samples (psi ~ 1e-6).
    versine = 2.0 * np.sin(0.5 * psi) ** 2

    bin_width = 2.0 * np.pi / azimuth_count
    bin_centres = np.arange(azimuth_count) * bin_width
    offsets = ((np.arange(subrays) + 0.5) / subrays - 0.5) * bin_width
    ray_azimuths = (bin_centres[:, None] + offsets[None, :]).ravel()

    ray_elevation = np.empty((len(heights_m), ray_azimuths.size))
    ray_distance = np.empty((len(heights_m), ray_azimuths.size))
    ray_covered = np.empty(ray_azimuths.size)
    for start in range(0, ray_azimuths.size, _AZIMUTH_CHUNK):
        azimuth = ray_azimuths[start : start + _AZIMUTH_CHUNK]
        chunk = slice(start, start + azimuth.size)
        heading = np.cos(azimuth)[:, None] * north + np.sin(azimuth)[:, None] * east
        # Unit vectors of the sample points, shape (rays, distances, 3).
        units = cos_psi[None, :, None] * up + sin_psi[None, :, None] * heading[:, None, :]
        x, y = south_polar_xy(units)
        del units
        point_radius = MOON_RADIUS_M + sample_terrains(terrains, x, y)
        has_data = ~np.isnan(point_radius)
        horizontal = point_radius * sin_psi
        drop = point_radius * versine
        rows = np.arange(azimuth.size)
        for index, observer_radius in enumerate(observer_radii):
            # r_p * cos(psi) - r_o, written as (r_p - r_o) - r_p * (1 - cos(psi)).
            elevation = np.arctan2((point_radius - observer_radius) - drop, horizontal)
            elevation[~has_data] = -np.inf
            best = np.argmax(elevation, axis=1)
            ray_elevation[index, chunk] = elevation[rows, best]
            ray_distance[index, chunk] = distances[best]
        # Distance of the last sample before the first gap in terrain coverage.
        first_gap = np.where(has_data.all(axis=1), distances.size, np.argmin(has_data, axis=1))
        ray_covered[chunk] = np.where(first_gap > 0, distances[np.maximum(first_gap, 1) - 1], 0.0)

    if np.isinf(ray_elevation[0].reshape(azimuth_count, subrays)).all(axis=1).any():
        raise ValueError("no terrain data along at least one azimuth")
    covered = ray_covered.reshape(azimuth_count, subrays).min(axis=1)
    bins = np.arange(azimuth_count)
    profiles = []
    for index, height in enumerate(heights_m):
        elevation = ray_elevation[index].reshape(azimuth_count, subrays)
        best_subray = np.argmax(elevation, axis=1)
        profiles.append(
            HorizonProfile(
                lat_rad=float(lat_rad),
                lon_east_rad=float(lon_east_rad),
                ground_height_m=ground_height,
                mast_height_m=height,
                max_range_m=float(max_range_m),
                azimuth_rad=bin_centres,
                elevation_rad=elevation[bins, best_subray],
                distance_m=ray_distance[index].reshape(azimuth_count, subrays)[bins, best_subray],
                covered_range_m=covered,
                terrain_names=tuple(terrain.name for terrain in terrains),
            )
        )
    return profiles
