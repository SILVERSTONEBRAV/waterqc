#core/templatetags/custom_filters.py
from django import template

register = template.Library()

_EMPTY = ""


def _safe_call(value):
    try:
        return value() if callable(value) else value
    except Exception:
        return _EMPTY


def _normalize(value):
    try:
        if value is None:
            return _EMPTY
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return value
        return str(value)
    except Exception:
        return _EMPTY


def _deep_getattr(obj, path):
    try:
        current = obj
        seen = set()

        for part in path.split("."):
            if current is None:
                return _EMPTY

            oid = id(current)
            if oid in seen:
                return _EMPTY
            seen.add(oid)

            current = getattr(current, part, None)
            current = _safe_call(current)

        return _normalize(current)

    except Exception:
        return _EMPTY


@register.filter(name="widget_name")
def widget_name(field):
    try:
        return field.field.widget.__class__.__name__
    except Exception:
        return _EMPTY


@register.filter(name="get_attr")
def get_attr(obj, attr):
    if not obj or not attr:
        return _EMPTY
    return _deep_getattr(obj, str(attr))


@register.filter(name="get_item")
def get_item(dictionary, key):
    """
    Return the actual item from a dict/mapping.
    Do not convert complex objects to strings.
    """
    try:
        if dictionary is None:
            return None

        if isinstance(dictionary, dict):
            return dictionary.get(key)

        if hasattr(dictionary, "get"):
            return dictionary.get(key)

        return None

    except Exception:
        return None


@register.filter(name="get")
def get(obj, key):
    try:
        if obj is None or key is None:
            return _EMPTY

        if isinstance(obj, dict):
            return _normalize(obj.get(key))

        value = getattr(obj, key, None)
        return _normalize(_safe_call(value))

    except Exception:
        return _EMPTY


@register.filter(name="get_display")
def get_display(obj, field_name):
    try:
        if not obj or not field_name:
            return _EMPTY

        display_method = f"get_{field_name}_display"

        if hasattr(obj, display_method):
            return _normalize(_safe_call(getattr(obj, display_method)))

        value = getattr(obj, field_name, None)
        return _normalize(_safe_call(value))

    except Exception:
        return _EMPTY


@register.filter(name="safe_str")
def safe_str(value):
    return _normalize(value)


@register.filter(name="attr_exists")
def attr_exists(obj, attr):
    try:
        return bool(obj and hasattr(obj, attr))
    except Exception:
        return False


@register.filter(name="is_dict")
def is_dict(value):
    return isinstance(value, dict)


@register.filter(name="is_list")
def is_list(value):
    return isinstance(value, list)


@register.filter(name="json_get")
def json_get(value, key):
    """
    Safe access for JSONField-like structures
    """
    try:
        if not isinstance(value, dict):
            return _EMPTY
        return _normalize(value.get(key))
    except Exception:
        return _EMPTY


@register.filter(name="chain_get")
def chain_get(obj, path):
    """
    Enhanced deep accessor for:
    object → dict → object mixed chains
    """
    try:
        if not obj or not path:
            return _EMPTY

        current = obj
        for part in str(path).split("."):
            if current is None:
                return _EMPTY

            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)

            current = _safe_call(current)

        return _normalize(current)

    except Exception:
        return _EMPTY


@register.filter(name="truthy")
def truthy(value):
    try:
        return bool(value)
    except Exception:
        return False


@register.filter(name="fallback")
def fallback(value, default):
    try:
        if value in (None, "", [], {}, False):
            return _normalize(default)
        return _normalize(value)
    except Exception:
        return _EMPTY

@register.filter(name="attr")
def attr(obj, key):
    try:
        if obj is None:
            return ""
        return getattr(obj, key, "")
    except Exception:
        return ""

@register.filter
def split_brackets(value):
    if not value or "(" not in value:
        return (value, "")
    idx = value.find("(")
    base = value[:idx].strip()
    extra = value[idx:].strip()
    return (base, extra)


