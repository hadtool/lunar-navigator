"""Environment smoke test: every dependency of the project can be imported."""

import importlib

import pytest

DEPENDENCIES = [
    "numpy",
    "scipy",
    "pandas",
    "pyarrow",
    "rasterio",
    "pyproj",
    "skyfield",
    "spiceypy",
    "requests",
    "streamlit",
    "plotly",
]


@pytest.mark.parametrize("module_name", DEPENDENCIES)
def test_dependency_imports(module_name: str) -> None:
    importlib.import_module(module_name)


def test_package_imports() -> None:
    import lunarnav

    assert lunarnav.__version__
