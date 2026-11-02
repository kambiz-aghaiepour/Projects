"""Safe AST-based expression engine for the scientific calculator.

The public entry point is :func:`evaluate`.  Expressions are parsed with
:func:`ast.parse` and every node is checked against a whitelist before
evaluation; Python's ``eval`` is never used.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable
from typing import Any, TypeAlias

Number: TypeAlias = int | float

MAX_EXPRESSION_LENGTH = 500
MAX_NODES = 200
MAX_FACTORIAL = 1000
MAX_EXPONENT = 10_000

CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _factorial(value: Number) -> int:
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("factorial expects a whole number")
        value = int(value)
    if value < 0 or value > MAX_FACTORIAL:
        raise ValueError(f"factorial expects an integer between 0 and {MAX_FACTORIAL}")
    return math.factorial(value)


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "sqrt": math.sqrt,
    "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "log": math.log,
    "ln": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "factorial": _factorial,
    "hypot": math.hypot,
    "degrees": math.degrees,
    "radians": math.radians,
}

TRIG_INPUTS = {"sin", "cos", "tan"}
INVERSE_TRIG = {"asin", "acos", "atan"}


class CalculatorError(ValueError):
    """Raised for invalid or unsafe expressions."""


def _validate(node: ast.AST) -> None:
    """Reject any AST node that is not part of the supported language."""
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Call,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.UAdd,
        ast.USub,
    )
    if not isinstance(node, allowed):
        raise CalculatorError(f"unsupported expression element: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _validate(child)


def _check_semantics(tree: ast.AST) -> None:
    """Validate names, calls, constants and dangerous exponents."""
    call_funcs = {
        id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise CalculatorError("only numeric literals are allowed")
        elif isinstance(node, ast.Name):
            if id(node) in call_funcs:
                continue
            if node.id not in CONSTANTS:
                raise CalculatorError(f"unknown name: {node.id!r}")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise CalculatorError("only direct function calls are allowed")
            if node.func.id not in FUNCTIONS:
                raise CalculatorError(f"function not allowed: {node.func.id!r}")
            if node.keywords:
                raise CalculatorError("keyword arguments are not supported")
            if len(node.args) > 2:
                raise CalculatorError("too many arguments in function call")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = node.right
            if isinstance(exponent, ast.Constant) and isinstance(exponent.value, int):
                if abs(exponent.value) > MAX_EXPONENT:
                    raise CalculatorError("exponent is too large")


def _eval(node: ast.AST, degrees: bool) -> Number:
    """Evaluate an already-validated AST."""
    if isinstance(node, ast.Expression):
        return _eval(node.body, degrees)
    if isinstance(node, ast.Constant):
        return node.value  # type: ignore[return-value]
    if isinstance(node, ast.Name):
        return CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, degrees)
        return +operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, degrees)
        right = _eval(node.right, degrees)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            if (
                isinstance(left, int)
                and isinstance(right, int)
                and right > 0
                and abs(left) > 1
                and left.bit_length() * right > 100_000
            ):
                raise CalculatorError("result would be too large")
            return left**right
        raise CalculatorError("unsupported binary operator")
    if isinstance(node, ast.Call):
        name = node.func.id  # type: ignore[attr-defined]
        args = [_eval(arg, degrees) for arg in node.args]
        if name in TRIG_INPUTS and degrees:
            args[0] = math.radians(args[0])
        result = FUNCTIONS[name](*args)
        if name in INVERSE_TRIG and degrees:
            result = math.degrees(result)
        return result
    raise CalculatorError("unsupported expression")


def evaluate(expression: str, degrees: bool = False) -> Number:
    """Safely evaluate a scientific expression."""
    expression = expression.strip()
    if not expression:
        raise CalculatorError("empty expression")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculatorError("expression is too long")
    expression = expression.replace("^", "**")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"invalid syntax: {exc.msg}") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise CalculatorError("expression is too complex")

    _validate(tree)
    _check_semantics(tree)
    try:
        result = _eval(tree, degrees)
    except ZeroDivisionError as exc:
        raise CalculatorError("division by zero") from exc
    except (OverflowError, MemoryError) as exc:
        raise CalculatorError("result is too large") from exc
    except TypeError as exc:
        raise CalculatorError(f"invalid function call: {exc}") from exc
    except ValueError as exc:
        raise CalculatorError(str(exc)) from exc

    if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
        raise CalculatorError("result is not a finite number")
    return result


def format_result(value: Number) -> str:
    """Render ints exactly and floats to 12 significant digits."""
    if isinstance(value, int):
        return str(value)
    text = f"{value:.12g}"
    return "0" if text == "-0" else text
