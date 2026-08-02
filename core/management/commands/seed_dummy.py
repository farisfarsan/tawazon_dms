from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import Client, Debtor, Case
from decimal import Decimal
import random


CLIENTS_DATA = [
    {"name": "Muscat Bank LLC",          "client_type": "bank",              "country": "Oman",          "city": "Muscat",      "phone": "+968 2400 1111", "email": "info@muscatbank.om",       "contact_person": "Ahmed Al Balushi",  "contract_type": "fixed_regular",    "status": "active"},
    {"name": "Gulf Finance Co.",          "client_type": "finance",           "country": "UAE",           "city": "Dubai",       "phone": "+971 4 555 2200", "email": "accounts@gulffinance.ae",  "contact_person": "Sara Al Mansoori",  "contract_type": "variable_regular", "status": "active"},
    {"name": "Oman Telecom Group",        "client_type": "telecommunication", "country": "Oman",          "city": "Muscat",      "phone": "+968 2450 0000", "email": "billing@omantelecom.om",   "contact_person": "Khalid Al Rashdi",  "contract_type": "fixed_regular",    "status": "active"},
    {"name": "Royal Medical Centre",      "client_type": "hospital",          "country": "Oman",          "city": "Salalah",     "phone": "+968 2323 4500", "email": "finance@rmc.om",           "contact_person": "Dr. Fatima Nasser", "contract_type": "one_time",         "status": "active"},
    {"name": "Al Jazeera Insurance",      "client_type": "insurance",         "country": "Qatar",         "city": "Doha",        "phone": "+974 4444 9900", "email": "claims@aljazeera-ins.qa",  "contact_person": "Ibrahim Al Sulaiti","contract_type": "variable_regular", "status": "active"},
    {"name": "Bahrain Hotel & Resort",    "client_type": "hotel",             "country": "Bahrain",       "city": "Manama",      "phone": "+973 1711 2200", "email": "accounting@bhr.bh",        "contact_person": "Maryam Yusuf",      "contract_type": "one_time",         "status": "active"},
    {"name": "National Education Trust",  "client_type": "education",         "country": "Oman",          "city": "Nizwa",       "phone": "+968 2541 3300", "email": "admin@neted.om",           "contact_person": "Salim Al Harthi",   "contract_type": "fixed_regular",    "status": "active"},
    {"name": "Al Futtaim Corp.",          "client_type": "corporate",         "country": "UAE",           "city": "Abu Dhabi",   "phone": "+971 2 626 0000", "email": "legal@alfuttaim.ae",       "contact_person": "Reem Al Zaabi",     "contract_type": "variable_regular", "status": "active"},
    {"name": "Kuwait Credit Agency",      "client_type": "agency",            "country": "Kuwait",        "city": "Kuwait City", "phone": "+965 2244 7700", "email": "ops@kca.kw",               "contact_person": "Tariq Al Mutairi",  "contract_type": "fixed_regular",    "status": "inactive"},
    {"name": "Saudi Merchant Group",      "client_type": "corporate",         "country": "Saudi Arabia",  "city": "Riyadh",      "phone": "+966 11 460 5500","email": "ar@saudimerchant.sa",      "contact_person": "Abdullah Al Ghamdi","contract_type": "one_time",         "status": "active"},
]

DEBTORS_DATA = [
    {"is_organization": False, "name": "Mohammed Al Hinai",      "first_name": "Mohammed",  "last_name": "Al Hinai",    "gender": "male",   "nationality": "Omani",   "country": "Oman",         "city": "Muscat",      "phone": "+968 9912 3456", "email": "m.hinai@email.com",         "status": "active"},
    {"is_organization": False, "name": "Fatima Bint Khalid",     "first_name": "Fatima",    "last_name": "Bint Khalid", "gender": "female", "nationality": "Emirati", "country": "UAE",          "city": "Dubai",       "phone": "+971 50 222 3344","email": "fatima.k@email.ae",         "status": "active"},
    {"is_organization": True,  "name": "Apex Trading LLC",       "cr_no": "CR-2019-004521", "occi_no": "OCC-7812",      "vatin_no": "VAT-OM-0044123", "country": "Oman",  "city": "Sohar",       "phone": "+968 2685 0011", "email": "info@apextrading.om",       "status": "active"},
    {"is_organization": False, "name": "Rashid Al Balushi",      "first_name": "Rashid",    "last_name": "Al Balushi",  "gender": "male",   "nationality": "Omani",   "country": "Oman",         "city": "Nizwa",       "phone": "+968 9811 7722", "email": "rashid.b@mail.com",         "status": "active"},
    {"is_organization": True,  "name": "Gulf Star Contracting",  "cr_no": "CR-2017-001134", "occi_no": "OCC-3301",      "vatin_no": "VAT-AE-0091874", "country": "UAE",   "city": "Sharjah",     "phone": "+971 6 553 7700", "email": "accounts@gulfstar.ae",     "status": "active"},
    {"is_organization": False, "name": "Amira Hassan Al Farsi",  "first_name": "Amira",     "last_name": "Al Farsi",    "gender": "female", "nationality": "Omani",   "country": "Oman",         "city": "Muscat",      "phone": "+968 9955 6611", "email": "amira.f@email.com",         "status": "active"},
    {"is_organization": False, "name": "Tariq Mahmoud Siddiqui", "first_name": "Tariq",     "last_name": "Siddiqui",    "gender": "male",   "nationality": "Pakistani","country": "Oman",         "city": "Salalah",     "phone": "+968 9700 4411", "email": "tariq.s@mail.com",          "status": "active"},
    {"is_organization": True,  "name": "Horizon Real Estate Co.","cr_no": "CR-2020-008876", "occi_no": "OCC-5599",      "vatin_no": "VAT-QA-0077211", "country": "Qatar", "city": "Doha",        "phone": "+974 4422 6600", "email": "legal@horizonre.qa",        "status": "active"},
    {"is_organization": False, "name": "Salwa Al Zadjali",       "first_name": "Salwa",     "last_name": "Al Zadjali",  "gender": "female", "nationality": "Omani",   "country": "Oman",         "city": "Muscat",      "phone": "+968 9833 5500", "email": "salwa.z@email.com",         "status": "active"},
    {"is_organization": True,  "name": "Prime Logistics SAOC",   "cr_no": "CR-2015-000312", "occi_no": "OCC-1140",      "vatin_no": "VAT-OM-0012009", "country": "Oman",  "city": "Muscat",      "phone": "+968 2448 7700", "email": "ops@primelogistics.om",     "status": "active"},
]

CASES_DATA = [
    {"client_idx": 0, "debtor_idx": 0, "approved": "12500.500", "received": "3000.000",  "status": "active"},
    {"client_idx": 1, "debtor_idx": 1, "approved": "48000.000", "received": "12000.000", "status": "contactable"},
    {"client_idx": 2, "debtor_idx": 2, "approved": "95000.750", "received": "0.000",     "status": "active"},
    {"client_idx": 3, "debtor_idx": 3, "approved": "7800.000",  "received": "7800.000",  "status": "closed"},
    {"client_idx": 4, "debtor_idx": 4, "approved": "220000.000","received": "50000.000", "status": "active"},
    {"client_idx": 5, "debtor_idx": 5, "approved": "15400.250", "received": "5000.000",  "status": "broken_promise"},
    {"client_idx": 6, "debtor_idx": 6, "approved": "33000.000", "received": "0.000",     "status": "active"},
    {"client_idx": 7, "debtor_idx": 7, "approved": "175000.000","received": "88000.000", "status": "contactable"},
    {"client_idx": 8, "debtor_idx": 8, "approved": "9200.000",  "received": "9200.000",  "status": "closed_by_client"},
    {"client_idx": 9, "debtor_idx": 9, "approved": "62500.000", "received": "18000.000", "status": "active"},
]


class Command(BaseCommand):
    help = "Seed 10 dummy clients, debtors, and cases"

    def handle(self, *args, **kwargs):
        admin = User.objects.filter(is_superuser=True).first()

        self.stdout.write("Creating clients...")
        clients = []
        for d in CLIENTS_DATA:
            c, created = Client.objects.get_or_create(
                name=d["name"],
                defaults={
                    "client_type": d["client_type"],
                    "country": d["country"],
                    "city": d["city"],
                    "phone": d["phone"],
                    "email": d["email"],
                    "contact_person": d["contact_person"],
                    "contract_type": d["contract_type"],
                    "status": d["status"],
                    "created_by": admin,
                }
            )
            clients.append(c)
            self.stdout.write(f"  {'Created' if created else 'Exists '} client: {c.name} ({c.client_id})")

        self.stdout.write("Creating debtors...")
        debtors = []
        for d in DEBTORS_DATA:
            defaults = {
                "is_organization": d["is_organization"],
                "country": d.get("country", "Oman"),
                "city": d.get("city", ""),
                "phone": d.get("phone", ""),
                "email": d.get("email", ""),
                "status": d.get("status", "active"),
                "created_by": admin,
            }
            if d["is_organization"]:
                defaults.update({
                    "cr_no": d.get("cr_no", ""),
                    "occi_no": d.get("occi_no", ""),
                    "vatin_no": d.get("vatin_no", ""),
                })
            else:
                defaults.update({
                    "first_name": d.get("first_name", ""),
                    "last_name": d.get("last_name", ""),
                    "gender": d.get("gender", ""),
                    "nationality": d.get("nationality", ""),
                })
            deb, created = Debtor.objects.get_or_create(name=d["name"], defaults=defaults)
            debtors.append(deb)
            self.stdout.write(f"  {'Created' if created else 'Exists '} debtor: {deb.name} ({deb.debtor_id})")

        self.stdout.write("Creating cases...")
        for d in CASES_DATA:
            client = clients[d["client_idx"]]
            debtor = debtors[d["debtor_idx"]]
            case, created = Case.objects.get_or_create(
                client=client,
                debtor=debtor,
                defaults={
                    "approved_amount": Decimal(d["approved"]),
                    "received_amount": Decimal(d["received"]),
                    "status": d["status"],
                    "collector": admin,
                }
            )
            self.stdout.write(f"  {'Created' if created else 'Exists '} case: {case.case_id} | {client.name} vs {debtor.name} | {d['status']}")

        self.stdout.write(self.style.SUCCESS("\nDone! 10 clients, 10 debtors, 10 cases seeded."))
