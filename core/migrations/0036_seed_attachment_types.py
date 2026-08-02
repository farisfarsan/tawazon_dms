from django.db import migrations

# (name, type)
TYPES = [
    # Client
    ("Contract",              "client"), ("Company Paper",          "client"),
    ("Bank Account Details",  "client"), ("Authorization Letter",   "client"),
    ("Power Of Attorney",     "client"), ("Trade License",          "client"),
    ("CR Certificate",        "client"),
    # Debtor
    ("Death Certificate",     "debtor"), ("ID",                     "debtor"),
    ("Passport",              "debtor"), ("Disability Certificate", "debtor"),
    ("Medical Report",        "debtor"), ("Salary Certificate",     "debtor"),
    ("Employment Letter",     "debtor"),
    # Case
    ("Agreement",             "case"),   ("LPO",                    "case"),
    ("SG",                    "case"),   ("Cheque Copy",            "case"),
    ("Clearance Letter",      "case"),   ("Travel Ban Release",     "case"),
    ("Court Fee Payment Proof","case"),  ("Invoice",                "case"),
    ("MOU",                   "case"),   ("Liability Letter",       "case"),
    ("Promissory Note",       "case"),   ("Warning Letter",         "case"),
    ("Payment Proof",         "case"),   ("Combined Documents",     "case"),
    ("Case Registration Proof","case"),  ("Judgments",              "case"),
    ("Facility Arbitration",  "case"),   ("Account Expert Proof",   "case"),
    ("Defense Judgment",      "case"),   ("Execution Proof",        "case"),
    ("Registration Proof",    "case"),   ("Arbitration Judgment",   "case"),
    ("Execution Judgment",    "case"),
]


def seed(apps, schema_editor):
    AttachmentType = apps.get_model('core', 'AttachmentType')
    for name, t in TYPES:
        AttachmentType.objects.get_or_create(name=name, defaults={'type': t})


def unseed(apps, schema_editor):
    apps.get_model('core', 'AttachmentType').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0035_attachmenttype')]
    operations = [migrations.RunPython(seed, unseed)]
