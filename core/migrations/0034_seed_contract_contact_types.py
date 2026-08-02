from django.db import migrations

CONTRACT_TYPES = ["One time", "Fixed Regular", "Variable Regular"]

# (name, type)
CONTACT_TYPES = [
    # Client contacts
    ("Accountant",             "client"), ("Chairman",             "client"),
    ("CFO",                    "client"), ("Managing Director",    "client"),
    ("Business Partner",       "client"), ("Director",             "client"),
    ("Employer",               "client"), ("Sales Administrator",  "client"),
    ("Legal Affairs Manager",  "client"), ("Admin",                "client"),
    ("Finance Manager",        "client"), ("Sales Manager",        "client"),
    ("Collection Manager",     "client"), ("Chief Finance Officer","client"),
    ("Operations Manager",     "client"), ("Credit Manager",       "client"),
    ("Collection Officer",     "client"), ("Managing Partner",     "client"),
    ("Operations Supervisor",  "client"), ("General Inspector",    "client"),
    ("Senior Partner",         "client"), ("Business Agent",       "client"),
    ("Owner",                  "client"), ("Subsidiary Manager",   "client"),
    ("Franchisee",             "client"), ("Auditor",              "client"),
    ("Contract Manager",       "client"), ("Assistant Manager",    "client"),
    ("General Manager",        "client"), ("HR Manager",           "client"),
    ("Branch Manager",         "client"), ("CEO",                  "client"),
    # Debtor contacts
    ("Accountant",             "debtor"), ("Director",             "debtor"),
    ("Employer",               "debtor"), ("Business Owner",       "debtor"),
    ("Cash Leader",            "debtor"), ("HR",                   "debtor"),
    ("Managing Director",      "debtor"), ("Owner",                "debtor"),
    ("Manager",                "debtor"), ("Business Manager",     "debtor"),
    ("Finance Director",       "debtor"), ("Supervisor",           "debtor"),
    ("Driver",                 "debtor"), ("MD for Limited",       "debtor"),
    ("General Manager",        "debtor"), ("Partner",              "debtor"),
    ("Spouse",                 "debtor"), ("Family Member",        "debtor"),
    ("Colleague",              "debtor"), ("Lawyer",               "debtor"),
    # Admin
    ("Admin",                  "admin"),  ("Super Admin",          "admin"),
]


def seed(apps, schema_editor):
    ContractType = apps.get_model('core', 'ContractType')
    ContactType  = apps.get_model('core', 'ContactType')
    for name in CONTRACT_TYPES:
        ContractType.objects.get_or_create(name=name)
    for name, t in CONTACT_TYPES:
        ContactType.objects.get_or_create(name=name, type=t)


def unseed(apps, schema_editor):
    apps.get_model('core', 'ContractType').objects.all().delete()
    apps.get_model('core', 'ContactType').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0033_contracttype_contacttype')]
    operations = [migrations.RunPython(seed, unseed)]
