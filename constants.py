import os

from dotenv import load_dotenv


load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN') if os.getlogin() == 'roman' else os.environ.get('BOT_PROD_TOKEN')

FIN_MON_ABBREVS = {
    'tam': 'tammikuuta',  # january
    'hel': 'helmikuuta',  # february
    'maa': 'maaliskuuta',  # march
    'huh': 'huhtikuuta',  # april
    'tou': 'toukokuuta',  # may
    'kes': 'kesäkuuta',  # june
    'hei': 'heinäkuuta',  # jule
    'elo': 'elokuuta',  # august
    'syy': 'syyskuuta',  # september
    'lok': 'lokakuuta',  # october
    'mar': 'marraskuuta',  # november
    'jou': 'joulukuuta'  # december
    }
TODAY = 'tänään'
YESTERDAY = 'eilen'


LOCATION_OPTIONS = {
    'Helsinki': 'ca=18&w=118&m=313',
    'Uusimaa': 'ca=18',
    'Tampere': 'ca=11&m=210&w=111',
    'Pirkanmaa': 'ca=11&w=1',
    'Turku': 'ca=16&w=116&m=297',
    'Varsinais-Suomi': 'ca=16',
    'Oulu': 'ca=2&w=102&m=39',
    'Pohjois-Pohjanmaa': 'ca=2',
    'Jyväskylä': 'ca=7&w=107&m=112',
    'Keski-Suomi': 'ca=7',
    'Any': 'w=3'
}

BID_TYPES = {
    'Free': 'st=g',
    'Selling': 'st=s',
    'Renting': 'st=u',
    'Any': 'st=s&st=g'
}

CATEGORIES = {
    'Vehicles and machines': 'cg=2000',
    'Apartments and properties': 'cg=1000',
    'Home and living': 'cg=3000',
    'Free time and hobbies': 'cg=4000',
    'Electronics': 'cg=5000',
    'Business and jobs': 'cg=6000',
    'Other': 'cg=7000',
    'Any': 'cg=0'
}

URL = 'https://www.tori.fi/'

MAX_ITEMS_PER_SEARCH = 5
MAX_ITEMS_ON_PAGE = 40

TRACKING_INTERVAL = 60 * 30  # 30 minutes
MAX_TRACKING_TIME = 60 * 60 * 24  # 24 hours
