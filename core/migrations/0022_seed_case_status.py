from django.db import migrations

# (name, color_hex)
STATUSES = [
    ("Active",                    "#4caf50"),
    ("Broken Promise",            "#fcfcfc"),
    ("Closed by Client request",  "#bf8b8d"),
    ("Closed by Compass Request", "#a9c96c"),
    ("Closed-Payment Done",       "#f51418"),
    ("Compass Request to close",  "#44495f"),
    ("Contactable",               "#e6e4d0"),
    ("Debtor Deceased",           "#000000"),
    ("Debtor in Jail",            "#fafafa"),
    ("Debtor Sick",               "#ffffff"),
    ("Hold by Client",            "#f9d51f"),
    ("Legal",                     "#1565c0"),
    ("New Case",                  "#90caf9"),
    ("No Contact",                "#ff7043"),
    ("On Hold",                   "#ffa726"),
    ("Paid in Full",              "#66bb6a"),
    ("Partial Payment",           "#26c6da"),
    ("Promise to Pay",            "#ab47bc"),
    ("Referred to Legal",         "#5c6bc0"),
    ("Settled",                   "#8d6e63"),
    ("Skip",                      "#ef5350"),
    ("Under Investigation",       "#78909c"),
    ("Uncontactable",             "#bdbdbd"),
    ("Written Off",               "#424242"),
]


def seed(apps, schema_editor):
    CaseStatus = apps.get_model('core', 'CaseStatus')
    for name, color in STATUSES:
        CaseStatus.objects.get_or_create(name=name, defaults={'color': color})


def unseed(apps, schema_editor):
    apps.get_model('core', 'CaseStatus').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0021_casestatus')]
    operations = [migrations.RunPython(seed, unseed)]
