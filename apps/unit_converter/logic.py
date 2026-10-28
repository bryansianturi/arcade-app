"""Unit definitions and exact conversions using :class:`decimal.Decimal`. No pygame.

Every linear unit is defined by how many base units it equals (metres,
kilograms, litres...). Temperature is affine, so it gets its own functions.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal

D = Decimal
CONTEXT = decimal.Context(prec=34)


@dataclass(frozen=True)
class Unit:
    symbol: str
    name: str
    factor: Decimal  # value of one of this unit in base units (unused for temperature)


@dataclass(frozen=True)
class Category:
    name: str
    units: tuple[Unit, ...]

    def unit(self, symbol: str) -> Unit:
        for u in self.units:
            if u.symbol == symbol:
                return u
        raise KeyError(symbol)


def _cat(name: str, *units: tuple[str, str, str]) -> Category:
    return Category(name, tuple(Unit(sym, label, D(factor)) for sym, label, factor in units))


CATEGORIES: tuple[Category, ...] = (
    _cat(
        "Length",
        ("mm", "Millimetre", "0.001"),
        ("cm", "Centimetre", "0.01"),
        ("m", "Metre", "1"),
        ("km", "Kilometre", "1000"),
        ("in", "Inch", "0.0254"),
        ("ft", "Foot", "0.3048"),
        ("yd", "Yard", "0.9144"),
        ("mi", "Mile", "1609.344"),
        ("nmi", "Nautical mile", "1852"),
    ),
    _cat(
        "Mass",
        ("mg", "Milligram", "0.000001"),
        ("g", "Gram", "0.001"),
        ("kg", "Kilogram", "1"),
        ("t", "Tonne", "1000"),
        ("oz", "Ounce", "0.028349523125"),
        ("lb", "Pound", "0.45359237"),
        ("st", "Stone", "6.35029318"),
    ),
    _cat("Temperature", ("°C", "Celsius", "1"), ("°F", "Fahrenheit", "1"), ("K", "Kelvin", "1")),
    _cat(
        "Volume",
        ("mL", "Millilitre", "0.001"),
        ("L", "Litre", "1"),
        ("m³", "Cubic metre", "1000"),
        ("tsp", "Teaspoon (US)", "0.00492892159375"),
        ("tbsp", "Tablespoon (US)", "0.01478676478125"),
        ("fl oz", "Fluid ounce (US)", "0.0295735295625"),
        ("cup", "Cup (US)", "0.2365882365"),
        ("pt", "Pint (US)", "0.473176473"),
        ("gal", "Gallon (US)", "3.785411784"),
    ),
    _cat(
        "Area",
        ("cm²", "Square centimetre", "0.0001"),
        ("m²", "Square metre", "1"),
        ("ha", "Hectare", "10000"),
        ("km²", "Square kilometre", "1000000"),
        ("in²", "Square inch", "0.00064516"),
        ("ft²", "Square foot", "0.09290304"),
        ("acre", "Acre", "4046.8564224"),
        ("mi²", "Square mile", "2589988.110336"),
    ),
    _cat(
        "Speed",
        ("m/s", "Metres per second", "1"),
        ("km/h", "Kilometres per hour", str(D(1) / D("3.6"))),
        ("mph", "Miles per hour", "0.44704"),
        ("kn", "Knot", str(D(1852) / D(3600))),
        ("ft/s", "Feet per second", "0.3048"),
    ),
    _cat(
        "Time",
        ("ms", "Millisecond", "0.001"),
        ("s", "Second", "1"),
        ("min", "Minute", "60"),
        ("h", "Hour", "3600"),
        ("d", "Day", "86400"),
        ("wk", "Week", "604800"),
        ("yr", "Year (365.25 d)", "31557600"),
    ),
    _cat(
        "Data",
        ("bit", "Bit", "0.125"),
        ("B", "Byte", "1"),
        ("KB", "Kilobyte", "1000"),
        ("MB", "Megabyte", "1000000"),
        ("GB", "Gigabyte", "1000000000"),
        ("TB", "Terabyte", "1000000000000"),
        ("KiB", "Kibibyte", "1024"),
        ("MiB", "Mebibyte", "1048576"),
        ("GiB", "Gibibyte", "1073741824"),
    ),
)

CATEGORY_BY_NAME = {c.name: c for c in CATEGORIES}


def _to_kelvin(value: Decimal, symbol: str) -> Decimal:
    if symbol == "°C":
        return value + D("273.15")
    if symbol == "°F":
        return (value - 32) * 5 / 9 + D("273.15")
    return value


def _from_kelvin(kelvin: Decimal, symbol: str) -> Decimal:
    if symbol == "°C":
        return kelvin - D("273.15")
    if symbol == "°F":
        return (kelvin - D("273.15")) * 9 / 5 + 32
    return kelvin


def convert(value: Decimal, category: Category, from_symbol: str, to_symbol: str) -> Decimal:
    """Convert ``value`` between two units of ``category``."""
    with decimal.localcontext(CONTEXT):
        if category.name == "Temperature":
            return _from_kelvin(_to_kelvin(value, from_symbol), to_symbol)
        return value * category.unit(from_symbol).factor / category.unit(to_symbol).factor


def parse_number(text: str) -> Decimal | None:
    """Parse input such as ``"1,250.5"``, ``"-3"`` or ``"2e3"``; ``None`` if it isn't a number."""
    cleaned = text.strip().replace(",", "").replace("−", "-").replace(" ", "")
    if not cleaned:
        return None
    try:
        value = D(cleaned)
    except decimal.InvalidOperation:
        return None
    return value if value.is_finite() else None


def format_value(value: Decimal, digits: int = 10) -> str:
    """Readable output: thousands separators, ≤ ``digits`` significant digits, no trailing zeros.

    Very large or very small magnitudes switch to scientific notation.
    """
    if value.is_zero():
        return "0"
    rounded = value.normalize(decimal.Context(prec=digits))
    exponent = rounded.adjusted()
    if -6 <= exponent < 15:
        text = f"{rounded:,f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text
    mantissa, _, exp = f"{rounded:e}".partition("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    return f"{mantissa}×10^{int(exp)}"
