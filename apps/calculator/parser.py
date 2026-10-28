"""A small, safe arithmetic parser (no ``eval``).

Grammar (standard precedence, ``^`` is right-associative)::

    expression := term (("+" | "-") term)*
    term       := unary (("*" | "/") unary | implicit_product)*
    unary      := ("+" | "-") unary | power
    power      := primary ("^" unary)?
    primary    := NUMBER | "(" expression ")"

Implicit multiplication is supported where it is unambiguous: ``2(3)``,
``(1+2)(3)`` and ``(2)3``. Arithmetic uses :class:`decimal.Decimal`, so
``0.1 + 0.2`` is exactly ``0.3``.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

TokenKind = Literal["num", "op", "lparen", "rparen"]

#: Display-friendly symbols accepted as aliases.
ALIASES = {"×": "*", "x": "*", "X": "*", "÷": "/", "−": "-", "–": "-", ",": "."}
OPERATORS = frozenset("+-*/^")
MAX_EXPONENT = 10_000
MAX_DIGITS = 12  # significant digits shown in results

_CONTEXT = decimal.Context(prec=34, Emax=999_999, Emin=-999_999)


class CalcError(Exception):
    """A user-facing error (bad syntax, division by zero...)."""


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    pos: int


def tokenize(source: str) -> list[Token]:
    """Split ``source`` into tokens, raising :class:`CalcError` on bad characters."""
    tokens: list[Token] = []
    i = 0
    while i < len(source):
        ch = ALIASES.get(source[i], source[i])
        if ch.isspace():
            i += 1
        elif ch.isdigit() or ch == ".":
            start = i
            dots = 0
            while i < len(source) and (
                source[i].isdigit() or ALIASES.get(source[i], source[i]) == "."
            ):
                dots += ALIASES.get(source[i], source[i]) == "."
                i += 1
            text = source[start:i].replace(",", ".")
            if dots > 1 or text == ".":
                raise CalcError(f"Invalid number '{text}'")
            i, exponent = _scan_exponent(source, i)
            tokens.append(Token("num", text + exponent, start))
        elif ch in OPERATORS:
            tokens.append(Token("op", ch, i))
            i += 1
        elif ch == "(":
            tokens.append(Token("lparen", ch, i))
            i += 1
        elif ch == ")":
            tokens.append(Token("rparen", ch, i))
            i += 1
        else:
            raise CalcError(f"Unexpected '{source[i]}'")
    return tokens


def _scan_exponent(source: str, i: int) -> tuple[int, str]:
    """Read an optional ``e±digits`` suffix (as produced by :func:`format_number`)."""
    if i >= len(source) or source[i] not in "eE":
        return i, ""
    j = i + 1
    sign = ""
    if j < len(source) and ALIASES.get(source[j], source[j]) in "+-":
        sign = ALIASES.get(source[j], source[j])
        j += 1
    start = j
    while j < len(source) and source[j].isdigit():
        j += 1
    if j == start:
        raise CalcError("Invalid number")
    return j, f"e{sign}{source[start:j]}"


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0

    def peek(self) -> Token | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> Token:
        tok = self.peek()
        if tok is None:
            raise CalcError("Incomplete expression")
        self.i += 1
        return tok

    def at_op(self, *ops: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == "op" and tok.text in ops

    def parse(self) -> Decimal:
        if not self.tokens:
            raise CalcError("Empty expression")
        value = self.expression()
        tok = self.peek()
        if tok is not None:
            raise CalcError("Unmatched ')'" if tok.kind == "rparen" else f"Unexpected '{tok.text}'")
        return value

    def expression(self) -> Decimal:
        value = self.term()
        while self.at_op("+", "-"):
            op = self.take().text
            rhs = self.term()
            value = _CONTEXT.add(value, rhs) if op == "+" else _CONTEXT.subtract(value, rhs)
        return value

    def term(self) -> Decimal:
        value = self.unary()
        while True:
            if self.at_op("*", "/"):
                op = self.take().text
                rhs = self.unary()
                if op == "*":
                    value = _CONTEXT.multiply(value, rhs)
                else:
                    if rhs == 0:
                        raise CalcError("Can't divide by zero")
                    value = _CONTEXT.divide(value, rhs)
            elif self._implicit_product():
                value = _CONTEXT.multiply(value, self.unary())
            else:
                return value

    def _implicit_product(self) -> bool:
        """``2(3)``, ``(2)(3)`` or ``(2)3``: a value directly followed by '(' or a number."""
        tok = self.peek()
        if tok is None or self.i == 0:
            return False
        prev = self.tokens[self.i - 1]
        return prev.kind in ("num", "rparen") and (
            tok.kind == "lparen" or (tok.kind == "num" and prev.kind == "rparen")
        )

    def unary(self) -> Decimal:
        if self.at_op("+", "-"):
            op = self.take().text
            value = self.unary()
            return -value if op == "-" else value
        return self.power()

    def power(self) -> Decimal:
        base = self.primary()
        if self.at_op("^"):
            self.take()
            exponent = self.unary()  # right-associative: 2^3^2 = 2^9
            return _pow(base, exponent)
        return base

    def primary(self) -> Decimal:
        tok = self.take()
        if tok.kind == "num":
            return Decimal(tok.text)
        if tok.kind == "lparen":
            value = self.expression()
            closing = self.peek()
            if closing is None or closing.kind != "rparen":
                raise CalcError("Missing ')'")
            self.take()
            return value
        if tok.kind == "rparen":
            raise CalcError("Unexpected ')'")
        raise CalcError(f"Unexpected '{tok.text}'")


def _pow(base: Decimal, exponent: Decimal) -> Decimal:
    if abs(exponent) > MAX_EXPONENT:
        raise CalcError("Number too large")
    if base == 0 and exponent < 0:
        raise CalcError("Can't divide by zero")
    try:
        return _CONTEXT.power(base, exponent)
    except decimal.InvalidOperation:
        raise CalcError("Not a real number") from None


def evaluate(source: str) -> Decimal:
    """Evaluate an arithmetic expression. Raises :class:`CalcError` on any problem."""
    try:
        result = _Parser(tokenize(source)).parse()
    except decimal.Overflow:
        raise CalcError("Number too large") from None
    except (decimal.InvalidOperation, decimal.DivisionByZero):
        raise CalcError("Invalid calculation") from None
    if not result.is_finite():
        raise CalcError("Number too large")
    return result


def format_number(value: Decimal, max_digits: int = MAX_DIGITS) -> str:
    """Format a result for display: at most ``max_digits`` significant digits.

    Uses plain notation for "normal" magnitudes and scientific notation for
    very large or very small numbers. Never shows ``-0`` or trailing zeros.
    """
    if value.is_zero():
        return "0"
    rounded = _CONTEXT.plus(value).normalize(decimal.Context(prec=max_digits))
    exponent = rounded.adjusted()  # power of ten of the leading digit
    if -7 < exponent < max_digits:
        text = f"{rounded:f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    mantissa, _, exp = f"{rounded:e}".partition("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    return f"{mantissa}e{int(exp):+d}"
