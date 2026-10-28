"""Calculator state machine: what each key press does to the expression."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.calculator.parser import CalcError, evaluate, format_number

DIGITS = frozenset("0123456789")
OPERATOR_KEYS = {"+": "+", "-": "−", "*": "×", "/": "÷", "^": "^"}
MAX_LENGTH = 64
HISTORY_SIZE = 8


@dataclass
class Calculator:
    """Holds the expression being typed, the last result and the history.

    Keys are single symbols: digits, ``.``, ``+ - * / ^``, ``(``, ``)``,
    ``=``, ``back`` and ``clear``. The expression is stored with display symbols
    (``×``, ``÷``, ``−``); the parser accepts them directly.
    """

    expression: str = ""
    error: str | None = None
    just_evaluated: bool = False
    history: list[tuple[str, str]] = field(default_factory=list)

    @property
    def preview(self) -> str | None:
        """The live result of the current expression, if it is complete and valid."""
        if not self.expression or self.just_evaluated:
            return None
        try:
            return format_number(evaluate(self.expression))
        except CalcError:
            return None

    def press(self, key: str) -> None:
        """Apply one key press."""
        if key == "clear":
            self.expression, self.error, self.just_evaluated = "", None, False
            return
        if self.error is not None:
            # Any key after an error starts over (except backspace, which just dismisses it).
            self.error = None
            if key == "back":
                return
            self.expression = ""
        if key == "back":
            self.expression = "" if self.just_evaluated else self.expression[:-1]
            self.just_evaluated = False
        elif key == "=":
            self._evaluate()
        elif key in DIGITS or key == "." or key == "(":
            if self.just_evaluated:
                self.expression = ""  # typing a number after "=" starts fresh
            self._append("0." if key == "." and not self._in_number() else key)
        elif key in OPERATOR_KEYS:
            self._append_operator(OPERATOR_KEYS[key])
        elif key == ")":
            self._append(key)

    def _in_number(self) -> bool:
        return bool(self.expression) and (
            self.expression[-1] in DIGITS or self.expression[-1] == "."
        )

    def _append(self, text: str) -> None:
        self.just_evaluated = False
        if text == "." and "." in self._current_number():
            return
        if len(self.expression) + len(text) <= MAX_LENGTH:
            self.expression += text

    def _append_operator(self, symbol: str) -> None:
        self.just_evaluated = False
        last = self.expression[-1:] if self.expression else ""
        if last in ("+", "−", "×", "÷", "^") and not (symbol == "−" and last != "−"):
            # Replace the previous operator instead of stacking them ("5+×" → "5×").
            self.expression = self.expression[:-1]
        self._append(symbol)

    def _current_number(self) -> str:
        i = len(self.expression)
        while i > 0 and (self.expression[i - 1] in DIGITS or self.expression[i - 1] == "."):
            i -= 1
        return self.expression[i:]

    def _evaluate(self) -> None:
        if not self.expression or self.just_evaluated:
            return
        # Be forgiving about unclosed parentheses: "2*(3+4" → "2*(3+4)".
        expr = self.expression + ")" * max(
            0, self.expression.count("(") - self.expression.count(")")
        )
        try:
            result = format_number(evaluate(expr))
        except CalcError as exc:
            self.error = str(exc)
            return
        self.history.insert(0, (expr, result))
        del self.history[HISTORY_SIZE:]
        self.expression = result.replace("-", "−")
        self.just_evaluated = True
