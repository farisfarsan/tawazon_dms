from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

register = template.Library()


@register.filter
def caseid_break(value):
    """Insert <wbr> break opportunities after each slash in a case id
    (e.g. TWZ/2026/08/0001) so it can wrap onto ~2 lines in a narrow column
    instead of forcing the column wide. Pair with the .caseid-2l CSS class."""
    if value is None:
        return ''
    return mark_safe(escape(str(value)).replace('/', '/<wbr>'))


@register.filter
def omr(value, decimal_places=3):
    try:
        decimal_places = int(decimal_places)
        val = Decimal(str(value))
        quantize_str = '0.' + '0' * decimal_places
        val = val.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
        negative = val < 0
        abs_val = abs(val)
        parts = str(abs_val).split('.')
        integer_part = '{:,}'.format(int(parts[0]))
        decimal_part = parts[1] if len(parts) > 1 else '0' * decimal_places
        sign = '-' if negative else ''
        return f'OMR {sign}{integer_part}.{decimal_part}'
    except (TypeError, ValueError, InvalidOperation):
        return f'OMR 0.{"0" * 3}'


@register.simple_tag
def status_color_css():
    """Emit CSS so every status-coloured element app-wide uses the colours
    configured in Settings → Case Status. Covers the All Cases status bar,
    case-detail badges, dashboard pills and generic status badges. Statuses
    with no configured colour keep each page's hardcoded fallback styling."""
    from django.utils.safestring import mark_safe
    from core.models import case_status_color_map

    def _luma(hexcolor):
        h = hexcolor.lstrip('#')
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        try:
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        except ValueError:
            return 0.5
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    rules = []
    for key, color in case_status_color_map().items():
        # Very light colours are invisible as text on white — keep the bar in
        # the exact colour but fall back to slate for the text/badge colour.
        text = color if _luma(color) < 0.72 else '#475569'
        rules.append(
            f'.status-bar.{key}{{background:{color} !important;}}'
            f'.status-bar-label.{key}{{color:{text} !important;}}'
            f'.case-status-badge.{key}{{background:color-mix(in srgb, {color} 16%, white) !important;color:{text} !important;}}'
            f'.s-pill.{key}{{background:color-mix(in srgb, {color} 16%, white) !important;color:{text} !important;}}'
            f'.s-badge.s-{key}{{background:color-mix(in srgb, {color} 16%, white) !important;color:{text} !important;}}'
            f'.badge.{key}{{background:color-mix(in srgb, {color} 16%, white) !important;color:{text} !important;}}'
        )
    return mark_safe('<style>' + ''.join(rules) + '</style>')


@register.filter
def flag(iso_code):
    """ISO 3166 two-letter code → flag emoji (e.g. 'OM' → 🇴🇲)."""
    code = (iso_code or '').strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ''
    return ''.join(chr(0x1F1E6 + ord(ch) - 65) for ch in code)
