"""Reader of docs/ENGINEERING_INPUTS.md, the file the team's engineer fills in.

The file is a set of Markdown tables with the columns key, parameter, value, units and
source. Only rows whose value cell is filled are returned; for everything else the models
fall back to placeholder values that are listed as assumptions in docs/ASSUMPTIONS.md.

Accepted value formats (decimal point or decimal comma):

* a number: ``0.3`` or ``0,3`` (a comma is always a decimal comma, never a thousands
  separator); text may follow the number, e.g. ``0.3 (BOL)``;
* a range with a default: ``0,5-2 (по умолчанию 1)`` or ``0.5-2 (default 1)``;
* a list: ``0; 2; 5; 10; 20`` (recommended) or ``0, 2, 5, 10, 20`` with a space after
  every separating comma, so ``2,5`` is the number 2.5 and ``2, 5`` two items;
* free text for the non-numeric rows (panel type, Earth visibility rule).

Fractions are written as 0..1; a value with a percent sign is refused instead of guessed.
A cell holding only a dash, ``TBD``, ``н/д`` or ``?`` counts as empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INPUTS_FILE = Path(__file__).resolve().parents[2] / "docs" / "ENGINEERING_INPUTS.md"

_NUMBER = r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?"
_SEPARATOR = r"(?:-|–|—|\.\.)"
_ROW = re.compile(r"^\|\s*`(?P<key>[a-z0-9_]+)`\s*\|(?P<rest>.*)\|\s*$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_RANGE = re.compile(
    rf"^\s*(?P<low>{_NUMBER})\s*{_SEPARATOR}\s*(?P<high>{_NUMBER})\s*"
    rf"\(\s*(?:по умолчанию|по умолч\.?|default)\s*[:=]?\s*(?P<default>{_NUMBER})\s*\)",
    re.IGNORECASE,
)
_LEADING_NUMBER = re.compile(rf"^\s*(?P<value>{_NUMBER})(?![\d.,])(?P<tail>.*)$")
_RANGE_WITHOUT_DEFAULT = re.compile(rf"^\s*{_SEPARATOR}\s*{_NUMBER}")
#: Cell contents that mean "not filled in yet".
_EMPTY_MARKS = {"", "-", "–", "—", "?", "tbd", "n/a", "н/д", "нет"}


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


@dataclass(frozen=True)
class EngineeringValue:
    """One filled row of the engineering inputs."""

    key: str
    raw: str
    source: str = ""

    def number(self) -> float:
        """The value as a number: the default of a range, otherwise the leading number."""
        match = _RANGE.match(self.raw)
        if match:
            return _to_float(match["default"])
        match = _LEADING_NUMBER.match(self.raw)
        if not match:
            raise ValueError(f"{self.key}: '{self.raw}' is not a number")
        if _RANGE_WITHOUT_DEFAULT.match(match["tail"]):
            raise ValueError(
                f"{self.key}: '{self.raw}' looks like a range without a default; "
                "write it as 'min-max (по умолчанию X)'"
            )
        if match["tail"].lstrip().startswith("%"):
            raise ValueError(f"{self.key}: '{self.raw}' has a percent sign; write fractions as 0..1")
        return _to_float(match["value"])

    def bounds(self) -> tuple[float, float] | None:
        """(minimum, maximum) when the value is written as a range, else None."""
        match = _RANGE.match(self.raw)
        if not match:
            return None
        low, high = _to_float(match["low"]), _to_float(match["high"])
        if low > high:
            raise ValueError(f"{self.key}: range '{self.raw}' has minimum above maximum")
        return low, high

    def numbers(self) -> list[float]:
        """The value as a list of numbers (``0, 2, 5`` or ``0; 2; 5``)."""
        items = [item for item in re.split(r";|,\s+", self.raw) if item.strip()]
        try:
            return [_to_float(item.strip()) for item in items]
        except ValueError as error:
            raise ValueError(f"{self.key}: '{self.raw}' is not a list of numbers") from error


def parse_engineering_inputs(text: str) -> dict[str, EngineeringValue]:
    """Filled rows of the Markdown tables, by key."""
    values: dict[str, EngineeringValue] = {}
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if not match:
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in _UNESCAPED_PIPE.split(match["rest"])]
        # cells: parameter, value, units, source
        if len(cells) < 2 or cells[1].lower() in _EMPTY_MARKS:
            continue
        key = match["key"]
        if key in values:
            raise ValueError(f"duplicate key '{key}' in the engineering inputs")
        values[key] = EngineeringValue(key, cells[1], cells[3] if len(cells) > 3 else "")
    return values


def load_engineering_inputs(path: str | Path | None = None) -> dict[str, EngineeringValue]:
    """Read the engineering inputs; a missing file gives an empty result."""
    path = Path(path) if path is not None else DEFAULT_INPUTS_FILE
    if not path.is_file():
        return {}
    return parse_engineering_inputs(path.read_text(encoding="utf-8"))
