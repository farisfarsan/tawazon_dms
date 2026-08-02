"""Country -> currency mapping.

Currency dropdowns across the dashboard are limited to the currencies of
the countries enabled in Settings -> Countries.  Enabling/disabling a
country there automatically adds/removes its currency everywhere a
currency select is shown (a Currency row with that code must also exist
and be enabled in Settings -> Currencies).
"""

# ISO-3166 alpha-2 country code -> ISO-4217 currency code
COUNTRY_CURRENCY = {
    'AF': 'AFN', 'AL': 'ALL', 'DZ': 'DZD', 'AD': 'EUR', 'AO': 'AOA',
    'AI': 'XCD', 'AG': 'XCD', 'AR': 'ARS', 'AM': 'AMD', 'AW': 'AWG',
    'AU': 'AUD', 'AT': 'EUR', 'AZ': 'AZN', 'BS': 'BSD', 'BH': 'BHD',
    'BD': 'BDT', 'BB': 'BBD', 'BY': 'BYN', 'BE': 'EUR', 'BZ': 'BZD',
    'BJ': 'XOF', 'BM': 'BMD', 'BT': 'BTN', 'BO': 'BOB', 'BA': 'BAM',
    'BW': 'BWP', 'BR': 'BRL', 'BN': 'BND', 'BG': 'BGN', 'BF': 'XOF',
    'BI': 'BIF', 'KH': 'KHR', 'CM': 'XAF', 'CA': 'CAD', 'CV': 'CVE',
    'KY': 'KYD', 'CF': 'XAF', 'TD': 'XAF', 'CL': 'CLP', 'CN': 'CNY',
    'CO': 'COP', 'KM': 'KMF', 'CG': 'XAF', 'CR': 'CRC', 'HR': 'EUR',
    'CU': 'CUP', 'CY': 'EUR', 'CZ': 'CZK', 'DK': 'DKK', 'DJ': 'DJF',
    'DM': 'XCD', 'DO': 'DOP', 'EC': 'USD', 'EG': 'EGP', 'SV': 'USD',
    'GQ': 'XAF', 'ER': 'ERN', 'EE': 'EUR', 'ET': 'ETB', 'FK': 'FKP',
    'FJ': 'FJD', 'FI': 'EUR', 'FR': 'EUR', 'GA': 'XAF', 'GM': 'GMD',
    'GE': 'GEL', 'DE': 'EUR', 'GH': 'GHS', 'GI': 'GIP', 'GR': 'EUR',
    'GL': 'DKK', 'GD': 'XCD', 'GP': 'EUR', 'GU': 'USD', 'GT': 'GTQ',
    'GN': 'GNF', 'GW': 'XOF', 'GY': 'GYD', 'HT': 'HTG', 'HN': 'HNL',
    'HK': 'HKD', 'HU': 'HUF', 'IS': 'ISK', 'IN': 'INR', 'ID': 'IDR',
    'IR': 'IRR', 'IQ': 'IQD', 'IE': 'EUR', 'IL': 'ILS', 'IT': 'EUR',
    'JM': 'JMD', 'JP': 'JPY', 'JO': 'JOD', 'KZ': 'KZT', 'KE': 'KES',
    'KW': 'KWD', 'KG': 'KGS', 'LA': 'LAK', 'LV': 'EUR', 'LB': 'LBP',
    'LS': 'LSL', 'LR': 'LRD', 'LY': 'LYD', 'LI': 'CHF', 'LT': 'EUR',
    'LU': 'EUR', 'MO': 'MOP', 'MG': 'MGA', 'MW': 'MWK', 'MY': 'MYR',
    'MV': 'MVR', 'ML': 'XOF', 'MT': 'EUR', 'MH': 'USD', 'MQ': 'EUR',
    'MR': 'MRU', 'MU': 'MUR', 'MX': 'MXN', 'MD': 'MDL', 'MC': 'EUR',
    'MN': 'MNT', 'ME': 'EUR', 'MA': 'MAD', 'MZ': 'MZN', 'MM': 'MMK',
    'NA': 'NAD', 'NP': 'NPR', 'NL': 'EUR', 'NZ': 'NZD', 'NI': 'NIO',
    'NE': 'XOF', 'NG': 'NGN', 'KP': 'KPW', 'MK': 'MKD', 'NO': 'NOK',
    'OM': 'OMR', 'PK': 'PKR', 'PS': 'ILS', 'PA': 'PAB', 'PG': 'PGK',
    'PY': 'PYG', 'PE': 'PEN', 'PH': 'PHP', 'PL': 'PLN', 'PT': 'EUR',
    'PR': 'USD', 'QA': 'QAR', 'RO': 'RON', 'RU': 'RUB', 'RW': 'RWF',
    'SA': 'SAR', 'SN': 'XOF', 'RS': 'RSD', 'SL': 'SLE', 'SG': 'SGD',
    'SK': 'EUR', 'SI': 'EUR', 'SB': 'SBD', 'SO': 'SOS', 'ZA': 'ZAR',
    'KR': 'KRW', 'SS': 'SSP', 'ES': 'EUR', 'LK': 'LKR', 'SD': 'SDG',
    'SR': 'SRD', 'SE': 'SEK', 'CH': 'CHF', 'SY': 'SYP', 'TW': 'TWD',
    'TJ': 'TJS', 'TZ': 'TZS', 'TH': 'THB', 'TL': 'USD', 'TG': 'XOF',
    'TO': 'TOP', 'TT': 'TTD', 'TN': 'TND', 'TR': 'TRY', 'TM': 'TMT',
    'UG': 'UGX', 'UA': 'UAH', 'AE': 'AED', 'GB': 'GBP', 'US': 'USD',
    'UY': 'UYU', 'UZ': 'UZS', 'VE': 'VES', 'VN': 'VND', 'YE': 'YER',
    'ZM': 'ZMW', 'ZW': 'ZWL',
}


def enabled_currency_codes():
    """Currency codes of the countries enabled in Settings -> Countries."""
    from .models import Country
    codes = set()
    for cc in Country.objects.filter(is_enabled=True).values_list('code', flat=True):
        cur = COUNTRY_CURRENCY.get((cc or '').strip().upper())
        if cur:
            codes.add(cur)
    return codes


def enabled_currencies(include_pks=None):
    """Enabled currencies restricted to enabled countries' currencies.

    include_pks: extra Currency pks to keep in the list regardless of the
    country filter (e.g. a case's already-saved currency).
    """
    from django.db.models import Q
    from .models import Currency
    q = Q(is_enabled=True, code__in=enabled_currency_codes())
    if include_pks:
        q |= Q(pk__in=[pk for pk in include_pks if pk])
    return Currency.objects.filter(q).order_by('code')
