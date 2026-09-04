from django import template

register = template.Library()


@register.filter
def basename(value):
    """Return the substring after the last "/" in a path-like value.

    Presentation defaulting for the technical-value primitive — malformed or
    awkward data degrades instead of raising in templates:

    - str (or anything coercible via str()): the text after the final "/";
      when there is no "/" at all, or the value ends with one (the result
      would be empty), the input string is returned unchanged.
    - None: rendered as "".
    """
    if value is None:
        return ""
    value = str(value)
    _, separator, tail = value.rpartition("/")
    return tail if separator and tail else value


@register.filter
def parent_dir(value):
    """Return the substring before the last "/" in a path-like value.

    Presentation defaulting for the technical-value primitive — malformed or
    awkward data degrades instead of raising in templates:

    - str (or anything coercible via str()): the text before the final "/",
      with no trailing slash; when there is no "/" at all, "" is returned.
    - None: rendered as "".
    """
    if value is None:
        return ""
    value = str(value)
    head, separator, _ = value.rpartition("/")
    return head if separator else ""
