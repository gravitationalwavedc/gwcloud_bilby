from django import template

register = template.Library()


@register.filter
def get_item(value, key):
    if isinstance(value, dict):
        return value.get(key)
    return None


@register.filter
def sort_items(value):
    if isinstance(value, dict):
        return sorted(value.items())
    return []


@register.filter
def human_value(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return None
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item.get("name"))
            else:
                parts.append(item)
        return ", ".join(str(p) for p in parts if p is not None)
    return value
