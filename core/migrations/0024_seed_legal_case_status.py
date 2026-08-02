from django.db import migrations

# (name, color_hex)
STATUSES = [
    ("Arbitration",                         ""),
    ("Closed by client request - Legal",    ""),
    ("Closed-by Compass Request",           "#e9a9ea"),
    ("Closed-Court Rejected",               ""),
    ("Closed-Payment done",                 ""),
    ("Contactable By Legal Department",     "#3df5d0"),
    ("Document Translation",                ""),
    ("Got Final Judgment",                  ""),
    ("In Appeal Hearing",                   ""),
    ("In Court / Announcement",             ""),
    ("In Court Hearing",                    ""),
    ("In Jail",                             ""),
    ("In Police",                           ""),
    ("Installment",                         ""),
    ("New Legal Case",                      ""),
    ("No Response from Lawyer",             ""),
    ("Pending Court Date",                  ""),
    ("Pending Judgment",                    ""),
    ("Referred to Lawyer",                  ""),
    ("Settled Out of Court",                ""),
    ("Under Investigation",                 ""),
    ("Waiting for Documents",               ""),
]


def seed(apps, schema_editor):
    LegalCaseStatus = apps.get_model('core', 'LegalCaseStatus')
    for name, color in STATUSES:
        LegalCaseStatus.objects.get_or_create(name=name, defaults={'color': color})


def unseed(apps, schema_editor):
    apps.get_model('core', 'LegalCaseStatus').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0023_legalcasestatus')]
    operations = [migrations.RunPython(seed, unseed)]
