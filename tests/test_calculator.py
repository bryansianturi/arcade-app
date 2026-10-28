from __future__ import annotations

from decimal import Decimal

import pytest

from apps.calculator.logic import Calculator
from apps.calculator.parser import CalcError, evaluate, format_number


def calc(expr: str) -> str:
    return format_number(evaluate(expr))


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("1+2*3", "7"),
        ("(1+2)*3", "9"),
        ("10-4-3", "3"),  # left associative
        ("100/10/5", "2"),
        ("2^3^2", "512"),  # right associative
        ("-2^2", "-4"),  # unary minus binds looser than ^
        ("(-2)^2", "4"),
        ("2^-1", "0.5"),
        ("0.1+0.2", "0.3"),  # Decimal, not float
        ("1/3", "0.333333333333"),
        ("2/3", "0.666666666667"),
        ("--3", "3"),
        ("+5", "5"),
        ("3 - -2", "5"),
        ("2(3+4)", "14"),  # implicit multiplication
        ("(1+1)(2+2)", "8"),
        ("(2)3", "6"),
        ("6×7", "42"),
        ("8÷2−1", "3"),
        (".5+.5", "1"),
        ("3.", "3"),
        ("1e3+1", "1001"),
        ("1.5e-3*2", "0.003"),
        ("2^0.5", "1.41421356237"),
        ("10^20", "1e+20"),
        ("1/10^8", "1e-8"),
        ("0*-1", "0"),  # never "-0"
    ],
)
def test_evaluate(expr: str, expected: str) -> None:
    assert calc(expr) == expected


@pytest.mark.parametrize(
    ("expr", "message"),
    [
        ("1/0", "divide by zero"),
        ("1/(2-2)", "divide by zero"),
        ("0^-1", "divide by zero"),
        ("", "Empty"),
        ("1+", "Incomplete"),
        ("(1+2", "Missing ')'"),
        ("1+2)", "Unmatched ')'"),
        ("()", "Unexpected ')'"),
        ("1..2", "Invalid number"),
        ("2*/3", "Unexpected '/'"),
        ("abc", "Unexpected 'a'"),
        ("__import__('os')", "Unexpected '_'"),
        ("(-8)^0.5", "Not a real number"),
        ("10^100000", "too large"),
        ("1e", "Invalid number"),
    ],
)
def test_errors(expr: str, message: str) -> None:
    with pytest.raises(CalcError, match=message.replace("(", r"\(").replace(")", r"\)")):
        evaluate(expr)


def test_format_number() -> None:
    assert format_number(Decimal("123.4500")) == "123.45"
    assert format_number(Decimal("-0.0")) == "0"
    assert format_number(Decimal("123456789012345")) == "1.23456789012e+14"
    assert format_number(Decimal("0.00000001234")) == "1.234e-8"


def press_all(c: Calculator, keys: str) -> Calculator:
    for k in keys:
        c.press(k)
    return c


def test_model_basic_flow() -> None:
    c = press_all(Calculator(), "12+3*2")
    assert c.expression == "12+3×2"
    assert c.preview == "18"
    c.press("=")
    assert c.expression == "18" and c.just_evaluated
    assert c.history == [("12+3×2", "18")]


def test_model_continue_from_result_or_start_fresh() -> None:
    c = press_all(Calculator(), "2+2=")
    c.press("*")
    assert c.expression == "4×"
    c = press_all(Calculator(), "2+2=")
    c.press("7")
    assert c.expression == "7"


def test_model_operator_replacement_and_negatives() -> None:
    c = press_all(Calculator(), "5+*")
    assert c.expression == "5×"
    c.press("-")  # allowed: multiply by a negative number
    assert c.expression == "5×−"
    press_all(c, "2=")
    assert c.expression == "−10"
    press_all(c, "+1=")  # results with display minus signs can be reused
    assert c.expression == "−9"


def test_model_decimal_point_rules() -> None:
    c = press_all(Calculator(), ".5.5")
    assert c.expression == "0.55"
    press_all(c, "+.")
    assert c.expression == "0.55+0."


def test_model_errors_and_recovery() -> None:
    c = press_all(Calculator(), "1/0=")
    assert c.error == "Can't divide by zero"
    assert c.expression == "1÷0"  # expression kept so the user can see it
    c.press("back")  # dismisses the error only
    assert c.error is None and c.expression == "1÷0"
    c = press_all(Calculator(), "1/0=")
    c.press("4")  # typing starts over
    assert c.error is None and c.expression == "4"


def test_model_auto_closes_parentheses_and_clear() -> None:
    c = press_all(Calculator(), "2*(3+4=")
    assert c.expression == "14"
    c.press("back")
    assert c.expression == ""
    press_all(c, "9")
    c.press("clear")
    assert c.expression == "" and c.preview is None


def test_model_large_results_round_trip() -> None:
    c = press_all(Calculator(), "10^20=")
    assert c.expression == "1e+20"
    press_all(c, "*2=")
    assert c.expression == "2e+20"
