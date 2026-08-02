from django.db import migrations

CURRENCIES = [
    # (name, code, symbol_left, symbol_right, value)
    ("Omani Rial",                   "OMR", "OMR",  "OMR",  "1.00000"),
    ("United Arab Emirates Dirham",  "AED", "AED",  "AED",  "9.52400"),
    ("Saudi Arabian Riyal",          "SAR", "SAR",  "SAR",  "9.75300"),
    ("Kuwaiti Dinar",                "KWD", "KWD",  "KWD",  "0.78900"),
    ("Bahraini Dinar",               "BHD", "BHD",  "BHD",  "0.97800"),
    ("Qatari Rial",                  "QAR", "QR",   "QAR",  "9.40800"),
    ("United States Dollar",         "USD", "$",    "USD",  "2.59067"),
    ("Euro",                         "EUR", "EUR",  "EUR",  "2.16100"),
    ("Indian Rupees",                "INR", "INR",  "INR",  "191.42000"),
    ("British Pound",                "GBP", "£",    "GBP",  "2.01000"),
    ("Pakistani Rupee",              "PKR", "PKR",  "PKR",  "720.00000"),
    ("Egyptian Pound",               "EGP", "EGP",  "EGP",  "127.00000"),
    ("Japanese Yen",                 "JPY", "¥",    "JPY",  "393.00000"),
    ("Chinese Yuan",                 "CNY", "¥",    "CNY",  "18.80000"),
    ("Canadian Dollar",              "CAD", "CA$",  "CAD",  "3.54000"),
    ("Australian Dollar",            "AUD", "A$",   "AUD",  "3.95000"),
    ("Swiss Franc",                  "CHF", "CHF",  "CHF",  "2.89000"),
    ("Turkish Lira",                 "TRY", "₺",    "TRY",  "84.00000"),
    ("South African Rand",           "ZAR", "R",    "ZAR",  "47.00000"),
    ("Malaysian Ringgit",            "MYR", "RM",   "MYR",  "11.80000"),
    ("Singapore Dollar",             "SGD", "S$",   "SGD",  "1.93000"),
    ("Philippine Peso",              "PHP", "₱",    "PHP",  "148.00000"),
    ("Indonesian Rupiah",            "IDR", "Rp",   "IDR",  "41000.00000"),
    ("Thai Baht",                    "THB", "฿",    "THB",  "91.00000"),
    ("Bangladeshi Taka",             "BDT", "BDT",  "BDT",  "284.00000"),
    ("Sri Lankan Rupee",             "LKR", "LKR",  "LKR",  "760.00000"),
    ("Jordanian Dinar",              "JOD", "JOD",  "JOD",  "1.83000"),
    ("Lebanese Pound",               "LBP", "LBP",  "LBP",  "232.00000"),
    ("Moroccan Dirham",              "MAD", "MAD",  "MAD",  "9.80000"),
    ("Nigerian Naira",               "NGN", "₦",    "NGN",  "4100.00000"),
    ("Kenyan Shilling",              "KES", "KES",  "KES",  "330.00000"),
    ("Ethiopian Birr",               "ETB", "ETB",  "ETB",  "122.00000"),
    ("Ghanaian Cedi",                "GHS", "GHS",  "GHS",  "36.00000"),
    ("Tanzanian Shilling",           "TZS", "TZS",  "TZS",  "6600.00000"),
]


def seed_currencies(apps, schema_editor):
    Currency = apps.get_model('core', 'Currency')
    for name, code, sym_l, sym_r, value in CURRENCIES:
        Currency.objects.get_or_create(name=name, defaults={
            'code': code, 'symbol_left': sym_l,
            'symbol_right': sym_r, 'value': value,
        })


def unseed_currencies(apps, schema_editor):
    apps.get_model('core', 'Currency').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0017_currency')]
    operations = [migrations.RunPython(seed_currencies, unseed_currencies)]
