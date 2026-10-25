"""Bounded expression parser/evaluator for configured laboratory formulas.

Only arithmetic, comparisons, conditional expressions, named inputs, and
explicit ``math`` functions are supported. No Python ``eval`` is used.
"""

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_FLOOR,
    localcontext,
)
import ast

from django.core.exceptions import ValidationError


ALLOWED_MATH_FUNCS = {
    "sqrt", "log", "log10", "exp", "pow", "fabs", "floor", "ceil",
}
ALLOWED_MATH_CONSTANTS = {"pi", "e"}
_MATH_CONSTANTS = {
    "pi": Decimal("3.141592653589793238462643383279503"),
    "e": Decimal("2.718281828459045235360287471352662"),
}
MAX_FORMULA_NODES = 128
MAX_POWER = Decimal("100")
MAX_ABS_RESULT = Decimal("1e14")

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.USub, ast.UAdd, ast.Not,
    ast.Constant, ast.Name, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Pow, ast.Mod, ast.Call, ast.Attribute, ast.Compare, ast.Eq,
    ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.BoolOp, ast.And,
    ast.Or, ast.IfExp,
)
_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_CMPOPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _parse(expression):
    if not isinstance(expression, str) or not expression.strip():
        raise ValidationError("A formula expression is required.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValidationError(f"Invalid formula syntax: {exc.msg}.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_FORMULA_NODES:
        raise ValidationError("The formula is too complex to evaluate.")
    for node in nodes:
        if not isinstance(node, _ALLOWED_NODES):
            raise ValidationError(f"Disallowed formula element: {type(node).__name__}.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise ValidationError("Formula constants must be numeric or boolean.")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or node.value.id != "math":
                raise ValidationError("Only approved math constants and functions are available.")
            if node.attr not in ALLOWED_MATH_FUNCS | ALLOWED_MATH_CONSTANTS:
                raise ValidationError(f"Unsupported math function or constant: {node.attr}.")
        if isinstance(node, ast.Call):
            if not (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "math"
                and node.func.attr in ALLOWED_MATH_FUNCS
            ):
                raise ValidationError("Calls must use an approved math function.")
            if node.keywords:
                raise ValidationError("Keyword arguments are not supported in formulas.")
    return tree


def validate_formula_expression(expr: str, *, allow_math_attr=True):
    if not allow_math_attr and "math." in str(expr):
        raise ValidationError("Math functions are not allowed in this formula.")
    tree = _parse(expr)
    return True if tree else False


def _number(value):
    if isinstance(value, bool):
        raise ValidationError("Boolean values cannot be used as measurements.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Formula inputs must be finite numeric values.") from exc
    if not result.is_finite():
        raise ValidationError("Formula inputs must be finite numeric values.")
    return result


def _check_result(value):
    if isinstance(value, Decimal):
        if not value.is_finite() or abs(value) >= MAX_ABS_RESULT:
            raise ValidationError("The formula produced an out-of-range result.")
    return value


def _evaluate(node, context):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, context)
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, bool) else _number(node.value)
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise ValidationError(f"The formula references undefined input '{node.id}'.")
        return context[node.id]
    if isinstance(node, ast.Attribute):
        if node.attr == "pi":
            return _MATH_CONSTANTS["pi"]
        if node.attr == "e":
            return _MATH_CONSTANTS["e"]
        raise ValidationError("A math function must be called with numeric arguments.")
    if isinstance(node, ast.BinOp):
        left = _number(_evaluate(node.left, context))
        right = _number(_evaluate(node.right, context))
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
            raise ValidationError("Formula exponents must be between -100 and 100.")
        try:
            return _check_result(_BINOPS[type(node.op)](left, right))
        except (ArithmeticError, InvalidOperation, OverflowError, ValueError) as exc:
            raise ValidationError(f"Formula arithmetic failed: {exc}.") from exc
    if isinstance(node, ast.UnaryOp):
        value = _evaluate(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not bool(value)
        number = _number(value)
        return -number if isinstance(node.op, ast.USub) else number
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not _evaluate(value, context):
                    return False
            return True
        for value in node.values:
            if _evaluate(value, context):
                return True
        return False
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, context)
        for operation, comparator in zip(node.ops, node.comparators):
            right = _evaluate(comparator, context)
            try:
                if not _CMPOPS[type(operation)](left, right):
                    return False
            except TypeError as exc:
                raise ValidationError("Formula comparisons use incompatible values.") from exc
            left = right
        return True
    if isinstance(node, ast.IfExp):
        branch = node.body if _evaluate(node.test, context) else node.orelse
        return _evaluate(branch, context)
    if isinstance(node, ast.Call):
        arguments_decimal = [_number(_evaluate(arg, context)) for arg in node.args]
        function_name = node.func.attr
        try:
            if function_name == "sqrt" and len(arguments_decimal) == 1:
                if arguments_decimal[0] < 0:
                    raise ValidationError("math.sqrt requires a non-negative measurement.")
                return _check_result(arguments_decimal[0].sqrt())
            if function_name == "fabs" and len(arguments_decimal) == 1:
                return abs(arguments_decimal[0])
            if function_name == "exp" and len(arguments_decimal) == 1:
                return _check_result(arguments_decimal[0].exp())
            if function_name == "log10" and len(arguments_decimal) == 1:
                if arguments_decimal[0] <= 0:
                    raise ValidationError("math.log10 requires a positive measurement.")
                return _check_result(arguments_decimal[0].log10())
            if function_name == "log" and len(arguments_decimal) in {1, 2}:
                value = arguments_decimal[0]
                if value <= 0:
                    raise ValidationError("math.log requires a positive measurement.")
                result = value.ln()
                if len(arguments_decimal) == 2:
                    base = arguments_decimal[1]
                    if base <= 0 or base == 1:
                        raise ValidationError("math.log base must be positive and different from one.")
                    result /= base.ln()
                return _check_result(result)
            if function_name == "pow" and len(arguments_decimal) == 2:
                base, exponent = arguments_decimal
                if abs(exponent) > MAX_POWER:
                    raise ValidationError("math.pow exponents must be between -100 and 100.")
                return _check_result(base ** exponent)
            if function_name == "floor" and len(arguments_decimal) == 1:
                return arguments_decimal[0].to_integral_value(rounding=ROUND_FLOOR)
            if function_name == "ceil" and len(arguments_decimal) == 1:
                return arguments_decimal[0].to_integral_value(rounding=ROUND_CEILING)
        except (ArithmeticError, InvalidOperation, OverflowError, ValueError) as exc:
            raise ValidationError(f"Math function {function_name} failed: {exc}.") from exc
        raise ValidationError(f"math.{function_name} received an unsupported number of arguments.")
    raise ValidationError(f"Unsupported formula node: {type(node).__name__}.")


def safe_eval_formula(formula: str, context: dict):
    tree = _parse(formula)
    safe_context = {
        key: value for key, value in context.items()
        if key != "math" and isinstance(key, str) and key.isidentifier()
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    unknown = names - safe_context.keys() - {"math"}
    if unknown:
        raise ValidationError("Undefined formula input(s): " + ", ".join(sorted(unknown)))
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        result = _evaluate(tree, safe_context)
    if isinstance(result, bool):
        raise ValidationError("The formula must return a numeric value.")
    return _check_result(_number(result))
