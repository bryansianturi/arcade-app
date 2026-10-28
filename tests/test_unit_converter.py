from __future__ import annotations

from decimal import Decimal

import pytest

from apps.unit_converter.logic import (
    CATEGORIES,
    CATEGORY_BY_NAME,
    Category,
    convert,
    format_value,
    parse_number,
)
from core.base_app import AppContext

D = Decimal


@pytest.mark.parametrize(
    ("value", "category", "src", "dst", "expected"),
    [
        ("1", "Length", "mi", "km", "1.609344"),
        ("3", "Length", "ft", "in", "36"),
        ("1", "Mass", "lb", "g", "453.59237"),
        ("100", "Temperature", "°C", "°F", "212"),
        ("-40", "Temperature", "°F", "°C", "-40"),
        ("0", "Temperature", "K", "°C", "-273.15"),
        ("1", "Volume", "gal", "L", "3.785411784"),
        ("1", "Area", "acre", "m²", "4,046.856422"),  # shown to 10 significant digits
        ("36", "Speed", "km/h", "m/s", "10"),
        ("1", "Time", "d", "min", "1,440"),
        ("1", "Data", "KiB", "bit", "8,192"),
    ],
)
def test_known_conversions(value: str, category: str, src: str, dst: str, expected: str) -> None:
    assert format_value(convert(D(value), CATEGORY_BY_NAME[category], src, dst)) == expected


@pytest.mark.parametrize("category", CATEGORIES, ids=lambda c: c.name)
def test_round_trips_are_exact_enough(category: Category) -> None:
    for a in category.units:
        for b in category.units:
            there = convert(D("123.456"), category, a.symbol, b.symbol)
            back = convert(there, category, b.symbol, a.symbol)
            assert abs(back - D("123.456")) < D("1e-20")


def test_symbols_are_unique_per_category() -> None:
    for c in CATEGORIES:
        symbols = [u.symbol for u in c.units]
        assert len(symbols) == len(set(symbols))


def test_parse_number() -> None:
    assert parse_number("1,250.5") == D("1250.5")
    assert parse_number(" −3 ") == D(-3)
    assert parse_number("2e3") == D(2000)
    for bad in ("", "abc", "1..2", "inf", "nan"):
        assert parse_number(bad) is None


def test_format_value() -> None:
    assert format_value(D("1234567.891")) == "1,234,567.891"
    assert format_value(D("0.1") + D("0.2")) == "0.3"
    assert format_value(D("1") / D("3")) == "0.3333333333"
    assert format_value(D("1e20")) == "1×10^20"
    assert format_value(D("0.00000001")) == "1×10^-8"
    assert format_value(D("-0.0")) == "0"


def test_app_converts_and_remembers(app_context: AppContext) -> None:
    from apps.unit_converter.app import UnitConverterApp

    app = UnitConverterApp(app_context)
    app.on_enter()
    app._set_category(2)  # Temperature
    app._set_unit("°C")
    app.value_input.set_text("37")
    assert app.value() == D(37)
    app.on_exit()
    again = UnitConverterApp(app_context)
    again.on_enter()
    assert (
        again.category.name == "Temperature"
        and again.from_symbol == "°C"
        and again.value_input.text == "37"
    )
