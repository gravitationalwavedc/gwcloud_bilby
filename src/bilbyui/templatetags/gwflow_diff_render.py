from collections.abc import Mapping, Sequence
from typing import Any

from django import template
from django.utils.html import format_html, format_html_join

register = template.Library()

_MAX_DEPTH = 6


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _label(key: Any) -> str:
    return str(key).replace("_", " ").capitalize()


def _render(value: Any, depth: int) -> str:
    if depth >= _MAX_DEPTH:
        return format_html("{}", str(value))

    if value is None:
        return format_html("{}", "Not provided")
    if value is True:
        return format_html("{}", "Yes")
    if value is False:
        return format_html("{}", "No")
    if isinstance(value, (int, float)) and value == 0:
        return format_html("{}", "0")
    if isinstance(value, Mapping):
        pairs = format_html_join(
            "",
            "<dt>{}</dt><dd>{}</dd>",
            ((_label(key), _render(item, depth + 1)) for key, item in value.items()),
        )
        return format_html("<dl>{}</dl>", pairs)
    if _is_list(value):
        if not value:
            return format_html("{}", "(none)")
        items = format_html_join(
            "",
            "<li>{}</li>",
            ((_render(item, depth + 1),) for item in value),
        )
        return format_html("<ul>{}</ul>", items)
    return format_html("{}", str(value))


@register.simple_tag
def render_diff_value(value: Any) -> str:
    """Render a JSON-like diff value as escaped, bounded structural HTML."""
    return _render(value, depth=0)
