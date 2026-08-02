from django.db import migrations

COUNTRIES = [
    ("Afghanistan", "AF", "+93"), ("Albania", "AL", "+355"), ("Algeria", "DZ", "+213"),
    ("Andorra", "AD", "+376"), ("Angola", "AO", "+244"), ("Anguilla", "AI", "+1264"),
    ("Antigua and Barbuda", "AG", "+1268"), ("Argentina", "AR", "+54"),
    ("Armenia", "AM", "+374"), ("Aruba", "AW", "+297"), ("Australia", "AU", "+61"),
    ("Austria", "AT", "+43"), ("Azerbaijan", "AZ", "+994"), ("Bahamas", "BS", "+1242"),
    ("Bahrain", "BH", "+973"), ("Bangladesh", "BD", "+880"), ("Barbados", "BB", "+1246"),
    ("Belarus", "BY", "+375"), ("Belgium", "BE", "+32"), ("Belize", "BZ", "+501"),
    ("Benin", "BJ", "+229"), ("Bermuda", "BM", "+1441"), ("Bhutan", "BT", "+975"),
    ("Bolivia", "BO", "+591"), ("Bosnia and Herzegovina", "BA", "+387"),
    ("Botswana", "BW", "+267"), ("Brazil", "BR", "+55"), ("Brunei", "BN", "+673"),
    ("Bulgaria", "BG", "+359"), ("Burkina Faso", "BF", "+226"), ("Burundi", "BI", "+257"),
    ("Cambodia", "KH", "+855"), ("Cameroon", "CM", "+237"), ("Canada", "CA", "+1"),
    ("Cape Verde", "CV", "+238"), ("Cayman Islands", "KY", "+1345"),
    ("Central African Republic", "CF", "+236"), ("Chad", "TD", "+235"),
    ("Chile", "CL", "+56"), ("China", "CN", "+86"), ("Colombia", "CO", "+57"),
    ("Comoros", "KM", "+269"), ("Congo", "CG", "+242"),
    ("Costa Rica", "CR", "+506"), ("Croatia", "HR", "+385"), ("Cuba", "CU", "+53"),
    ("Cyprus", "CY", "+357"), ("Czech Republic", "CZ", "+420"),
    ("Denmark", "DK", "+45"), ("Djibouti", "DJ", "+253"), ("Dominica", "DM", "+1767"),
    ("Dominican Republic", "DO", "+1809"), ("Ecuador", "EC", "+593"),
    ("Egypt", "EG", "+20"), ("El Salvador", "SV", "+503"),
    ("Equatorial Guinea", "GQ", "+240"), ("Eritrea", "ER", "+291"),
    ("Estonia", "EE", "+372"), ("Ethiopia", "ET", "+251"),
    ("Falkland Islands", "FK", "+500"), ("Fiji", "FJ", "+679"),
    ("Finland", "FI", "+358"), ("France", "FR", "+33"), ("Gabon", "GA", "+241"),
    ("Gambia", "GM", "+220"), ("Georgia", "GE", "+995"), ("Germany", "DE", "+49"),
    ("Ghana", "GH", "+233"), ("Gibraltar", "GI", "+350"), ("Greece", "GR", "+30"),
    ("Greenland", "GL", "+299"), ("Grenada", "GD", "+1473"),
    ("Guadeloupe", "GP", "+590"), ("Guam", "GU", "+1671"), ("Guatemala", "GT", "+502"),
    ("Guinea", "GN", "+224"), ("Guinea-Bissau", "GW", "+245"),
    ("Guyana", "GY", "+592"), ("Haiti", "HT", "+509"), ("Honduras", "HN", "+504"),
    ("Hong Kong", "HK", "+852"), ("Hungary", "HU", "+36"), ("Iceland", "IS", "+354"),
    ("India", "IN", "+91"), ("Indonesia", "ID", "+62"), ("Iran", "IR", "+98"),
    ("Iraq", "IQ", "+964"), ("Ireland", "IE", "+353"), ("Israel", "IL", "+972"),
    ("Italy", "IT", "+39"), ("Jamaica", "JM", "+1876"), ("Japan", "JP", "+81"),
    ("Jordan", "JO", "+962"), ("Kazakhstan", "KZ", "+7"), ("Kenya", "KE", "+254"),
    ("Kuwait", "KW", "+965"), ("Kyrgyzstan", "KG", "+996"), ("Laos", "LA", "+856"),
    ("Latvia", "LV", "+371"), ("Lebanon", "LB", "+961"), ("Lesotho", "LS", "+266"),
    ("Liberia", "LR", "+231"), ("Libya", "LY", "+218"), ("Liechtenstein", "LI", "+423"),
    ("Lithuania", "LT", "+370"), ("Luxembourg", "LU", "+352"),
    ("Macau", "MO", "+853"), ("Madagascar", "MG", "+261"), ("Malawi", "MW", "+265"),
    ("Malaysia", "MY", "+60"), ("Maldives", "MV", "+960"), ("Mali", "ML", "+223"),
    ("Malta", "MT", "+356"), ("Marshall Islands", "MH", "+692"),
    ("Martinique", "MQ", "+596"), ("Mauritania", "MR", "+222"),
    ("Mauritius", "MU", "+230"), ("Mexico", "MX", "+52"), ("Moldova", "MD", "+373"),
    ("Monaco", "MC", "+377"), ("Mongolia", "MN", "+976"), ("Montenegro", "ME", "+382"),
    ("Morocco", "MA", "+212"), ("Mozambique", "MZ", "+258"), ("Myanmar", "MM", "+95"),
    ("Namibia", "NA", "+264"), ("Nepal", "NP", "+977"), ("Netherlands", "NL", "+31"),
    ("New Zealand", "NZ", "+64"), ("Nicaragua", "NI", "+505"), ("Niger", "NE", "+227"),
    ("Nigeria", "NG", "+234"), ("North Korea", "KP", "+850"),
    ("North Macedonia", "MK", "+389"), ("Norway", "NO", "+47"), ("Oman", "OM", "+968"),
    ("Pakistan", "PK", "+92"), ("Palestine", "PS", "+970"), ("Panama", "PA", "+507"),
    ("Papua New Guinea", "PG", "+675"), ("Paraguay", "PY", "+595"),
    ("Peru", "PE", "+51"), ("Philippines", "PH", "+63"), ("Poland", "PL", "+48"),
    ("Portugal", "PT", "+351"), ("Puerto Rico", "PR", "+1787"), ("Qatar", "QA", "+974"),
    ("Romania", "RO", "+40"), ("Russia", "RU", "+7"), ("Rwanda", "RW", "+250"),
    ("Saudi Arabia", "SA", "+966"), ("Senegal", "SN", "+221"), ("Serbia", "RS", "+381"),
    ("Sierra Leone", "SL", "+232"), ("Singapore", "SG", "+65"),
    ("Slovakia", "SK", "+421"), ("Slovenia", "SI", "+386"),
    ("Solomon Islands", "SB", "+677"), ("Somalia", "SO", "+252"),
    ("South Africa", "ZA", "+27"), ("South Korea", "KR", "+82"),
    ("South Sudan", "SS", "+211"), ("Spain", "ES", "+34"), ("Sri Lanka", "LK", "+94"),
    ("Sudan", "SD", "+249"), ("Suriname", "SR", "+597"), ("Sweden", "SE", "+46"),
    ("Switzerland", "CH", "+41"), ("Syria", "SY", "+963"), ("Taiwan", "TW", "+886"),
    ("Tajikistan", "TJ", "+992"), ("Tanzania", "TZ", "+255"), ("Thailand", "TH", "+66"),
    ("Timor-Leste", "TL", "+670"), ("Togo", "TG", "+228"), ("Tonga", "TO", "+676"),
    ("Trinidad and Tobago", "TT", "+1868"), ("Tunisia", "TN", "+216"),
    ("Turkey", "TR", "+90"), ("Turkmenistan", "TM", "+993"),
    ("Uganda", "UG", "+256"), ("Ukraine", "UA", "+380"),
    ("United Arab Emirates", "AE", "+971"), ("United Kingdom", "GB", "+44"),
    ("United States", "US", "+1"), ("Uruguay", "UY", "+598"),
    ("Uzbekistan", "UZ", "+998"), ("Venezuela", "VE", "+58"), ("Vietnam", "VN", "+84"),
    ("Yemen", "YE", "+967"), ("Zambia", "ZM", "+260"), ("Zimbabwe", "ZW", "+263"),
]

ENABLED = {"Oman", "United Arab Emirates", "Saudi Arabia", "Kuwait", "Qatar",
           "Bahrain", "Afghanistan", "Australia"}


def seed_countries(apps, schema_editor):
    Country = apps.get_model('core', 'Country')
    for name, code, dial in COUNTRIES:
        Country.objects.get_or_create(
            name=name,
            defaults={'code': code, 'country_code': dial, 'is_enabled': name in ENABLED}
        )


def unseed_countries(apps, schema_editor):
    apps.get_model('core', 'Country').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0013_country')]
    operations = [migrations.RunPython(seed_countries, unseed_countries)]
