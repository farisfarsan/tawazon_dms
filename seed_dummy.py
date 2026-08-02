import os, sys, django, random
from decimal import Decimal
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
sys.path.insert(0, '/home/faris/Desktop/collection_dashboard')
django.setup()

from core.models import Client, Debtor, Case

random.seed(99)

# ── Building blocks ─────────────────────────────────────────────────────────

CLIENT_PREFIXES = [
    "Gulf","Muscat","Oman","National","Royal","Al Jazeera","Bahrain","Saudi",
    "Al Futtaim","Emirates","Kuwait","Doha","Apex","Pinnacle","Crescent",
    "Horizon","Blue Sea","Sunrise","Pacific","Golden Gate","Falcon","Cedar",
    "Petra","Delta","Meridian","Zenith","Atlas","Orion","Nova","Stellar",
    "Arabian","Khaleeji","Masdar","Tamkeen","Majan","Ruwi","Seeb","Salalah",
    "Nizwa","Sohar","Ibri","Sur","Barka","Khasab","Haima","Duqm","Saham",
    "Rustaq","Liwa","Musandam","Dhofar","Batinah","Dakhliyah","Sharqiyah",
    "Wusta","Buraimi","Sib","Azaiba","Qurum","Khuwair","Madinat","Amerat",
    "Hamriya","Quriyat","Izki","Manah","Bahla","Adam","Hajer","Ibra",
    "Bidiyah","Mahout","Sinaw","Hayma","Shuwaymiyyah","Thumrait","Mirbat",
    "Sadah","Qalhat","Diba","Khor","Masirah","Jalan","Mudaybi","Wadi",
    "Samail","Fanja","Bidbid","Sumayil","Aldakiliyah","Aldahira","Mushraf",
    "Muttrah","Bawshar","Ghala","Wattayah","Ruwi","Darsait","Hamdan",
    "Rashid","Zayed","Nahyan","Maktoum","Khalifa","Nasser","Sultan","Qaboos",
]

CLIENT_SUFFIXES = [
    "Finance Co.","Bank LLC","Telecom Group","Education Trust","Medical Centre",
    "Insurance","Hotel & Resort","Merchant Group","Corp.","Trading Ltd",
    "Finance House","Holdings","Solutions","Services","Group","Enterprises",
    "Investments","Properties","Logistics","Healthcare","Technologies","Capital",
    "Consulting","Associates","Partners","International","Industries","Ventures",
    "Management","Development","Real Estate","Exports","Imports","Manufacturing",
]

CLIENT_TYPES = ["agency","bank","telecommunication","education","hospital",
                "insurance","hotel","corporate","finance","other"]

CONTACT_FIRST = ["Ali","Sara","Khalid","Fatima","Mohammed","Mona","Ibrahim",
                 "Leila","Tariq","Nadia","Omar","Aisha","Salim","Hana","Yousef",
                 "Rania","Faisal","Samira","Rashid","Layla","Ahmed","Saud",
                 "Hamad","Noura","Waleed","Mariam","Saeed","Reem","Jassim","Hessa"]

CONTACT_LAST  = ["Hassan","Al Balushi","Al Said","Al Zahra","Nasser","Al Hashmi",
                 "Al Wahaibi","Mansour","Al Rashid","Khalil","Al Lawati","Al Farsi",
                 "Al Bulushi","Al Amri","Al Habsi","Hamed","Al Ghafri","Zayed",
                 "Al Mutairi","Al Thani","Al Qasimi","Al Nuaimi","Al Maktoum",
                 "Al Nahyan","Bin Laden","Al Sabah","Al Khalifa","Al Saud"]

DEBTOR_FIRST_M = ["Ahmed","Mohammed","Khalid","Ibrahim","Omar","Salim","Faisal",
                  "Rashid","Yousef","Ali","Hassan","Tariq","Waleed","Saeed","Jassim",
                  "Hamad","Saud","Nasser","Sultan","Majid","Badar","Hilal","Talal",
                  "Mansour","Fahad","Abdulla","Bader","Nawaf","Turki","Adel","Essa",
                  "Mubarak","Jasim","Raed","Ziad","Osama","Hatem","Khaled","Samer","Wael"]

DEBTOR_FIRST_F = ["Fatima","Sara","Mona","Leila","Nadia","Aisha","Hana","Rania",
                  "Samira","Layla","Noura","Mariam","Hessa","Reem","Sheikha","Amna",
                  "Maryam","Shaikha","Latifa","Maitha","Khawla","Afra","Meera","Asma",
                  "Dana","Lulua","Shamsa","Hind","Ohoud","Moza"]

DEBTOR_LAST   = ["Al Rashid","Al Balushi","Al Zadjali","Nasser","Al Hashmi",
                 "Al Said","Al Qasmi","Mohammed","Hassan","Khalil","Al Lawati",
                 "Al Habsi","Al Ghafri","Al Farsi","Al Bulushi","Al Amri","Hamed",
                 "Al Wahaibi","Al Mutairi","Al Thani","Al Nuaimi","Al Maktoum",
                 "Bin Ali","Al Sabah","Al Khalifa","Al Saud","Al Nahyan","Al Falasi",
                 "Al Mheiri","Al Zaabi","Al Ketbi","Al Qubaisi","Al Shamsi",
                 "Al Kaabi","Al Mazrouei","Al Hammadi","Al Suwaidi","Al Muhairi"]

CITIES_OMAN   = ["Muscat","Salalah","Nizwa","Sohar","Sur","Ibra","Barka",
                 "Rustaq","Saham","Ibri","Bahla","Adam","Khasab","Duqm","Haima"]
CITIES_UAE    = ["Dubai","Abu Dhabi","Sharjah","Ajman","RAK","Fujairah","UAQ"]
CITIES_GCC    = ["Riyadh","Jeddah","Dammam","Kuwait","Manama","Doha","Sana'a"]

COUNTRIES = (["Oman"]*50) + (["UAE"]*20) + (["Saudi Arabia"]*15) + \
            (["Kuwait"]*5) + (["Bahrain"]*5) + (["Qatar"]*5)

STATUSES = ['active','broken_promise','contactable','closed','closed_by_client']

def city_for(country):
    if country == "Oman":        return random.choice(CITIES_OMAN)
    if country == "UAE":         return random.choice(CITIES_UAE)
    return random.choice(CITIES_GCC)

def phone(prefix="+968"):
    return f"{prefix} {random.randint(9000,9999)} {random.randint(1000,9999)}"

def email(name, idx):
    domains = ["gmail.com","hotmail.com","yahoo.com","outlook.com","icloud.com"]
    slug = name.lower().replace(" ","").replace(".","")[:12]
    return f"{slug}{idx}@{random.choice(domains)}"

# ── Generate 100 unique client records ──────────────────────────────────────

seen_cnames = set(Client.objects.values_list('name', flat=True))
new_clients = []
idx = 0
while len(new_clients) < 100:
    name = f"{random.choice(CLIENT_PREFIXES)} {random.choice(CLIENT_SUFFIXES)}"
    if name in seen_cnames:
        continue
    seen_cnames.add(name)
    ctype   = random.choice(CLIENT_TYPES)
    contact = f"{random.choice(CONTACT_FIRST)} {random.choice(CONTACT_LAST)}"
    country = random.choice(["Oman","UAE","Saudi Arabia","Kuwait","Bahrain"])
    ph = phone("+968" if country=="Oman" else "+971" if country=="UAE"
               else "+966" if country=="Saudi Arabia" else "+965" if country=="Kuwait" else "+973")
    new_clients.append(dict(
        name=name, client_type=ctype, phone=ph,
        email=email(name, idx), contact_person=contact,
        country=country, status='active',
    ))
    idx += 1

# ── Generate 100 unique debtor records ──────────────────────────────────────

seen_dnames = set(Debtor.objects.values_list('name', flat=True))
new_debtors = []
idx = 0
while len(new_debtors) < 100:
    gender = random.choice(["male","female"])
    first  = random.choice(DEBTOR_FIRST_M if gender=="male" else DEBTOR_FIRST_F)
    last   = random.choice(DEBTOR_LAST)
    name   = f"{first} {last}"
    if name in seen_dnames:
        continue
    seen_dnames.add(name)
    country = random.choice(COUNTRIES)
    new_debtors.append(dict(
        name=name, first_name=first, last_name=last,
        gender=gender, email=email(name, idx),
        phone=phone("+968"), city=city_for(country),
        country=country, status='active',
    ))
    idx += 1

# ── Insert clients ───────────────────────────────────────────────────────────

print(f"Inserting {len(new_clients)} clients...")
created_clients = []
for d in new_clients:
    c = Client.objects.create(**d)
    created_clients.append(c)
print(f"  Done. Total clients: {Client.objects.count()}")

# ── Insert debtors ───────────────────────────────────────────────────────────

print(f"Inserting {len(new_debtors)} debtors...")
created_debtors = []
for d in new_debtors:
    db = Debtor.objects.create(**d)
    created_debtors.append(db)
print(f"  Done. Total debtors: {Debtor.objects.count()}")

# ── Insert 100 cases ─────────────────────────────────────────────────────────

print("Inserting 100 cases...")
all_clients = list(Client.objects.all())
all_debtors = list(Debtor.objects.all())

existing_pairs = set(Case.objects.values_list('client_id','debtor_id'))
cases_created  = 0
attempts       = 0

while cases_created < 100 and attempts < 5000:
    attempts += 1
    client = random.choice(all_clients)
    debtor = random.choice(all_debtors)
    pair   = (client.pk, debtor.pk)
    if pair in existing_pairs:
        continue
    existing_pairs.add(pair)

    approved      = Decimal(str(round(random.uniform(300, 80000), 3)))
    received      = Decimal(str(round(float(approved) * random.uniform(0, 0.9), 3)))
    days_ago      = random.randint(10, 900)
    received_date = date.today() - timedelta(days=days_ago)
    due_date      = received_date + timedelta(days=random.randint(60, 540))

    Case.objects.create(
        client=client, debtor=debtor,
        approved_amount=approved, received_amount=received,
        status=random.choice(STATUSES),
        received_date=received_date, due_date=due_date,
        case_country=debtor.country or 'Oman',
    )
    cases_created += 1

print(f"  Done. Total cases: {Case.objects.count()}")
print(f"\nFinal totals → Clients: {Client.objects.count()} | Debtors: {Debtor.objects.count()} | Cases: {Case.objects.count()}")
