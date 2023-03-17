import os

from dotenv import load_dotenv


load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN') if os.getenv('USER') == 'roman' else os.environ.get('BOT_TOKEN_PROD')

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
    'Any': 'w=3',
    'Rovaniemi': 'ca=1&w=101&m=13',
    'Lappi': 'ca=1',
    'Kajaani': 'ca=3&w=103&m=57',
    'Kainuu': 'ca=3',
    'Joensuu': 'ca=9&w=109&m=157',
    'Pohjois-Karjala': 'ca=9',
    'Kuopio': 'ca=8&w=108&m=139',
    'Pohjois-Savo': 'ca=8',
    'Mikkeli': 'ca=13&w=113&m=235',
    'Etelä-Savo': 'ca=13',
    'Lappeenranta': 'ca=14&w=114&m=246',
    'Etelä-Karjala': 'ca=14',
    'Seinäjoki': 'ca=6&w=106&m=104',
    'Etelä-Pohjanmaa': 'ca=6',
    'Vaasa': 'ca=5&w=105&m=88',
    'Pohjanmaa': 'ca=5',
    'Kokkola': 'ca=4&w=104&m=69',
    'Keski-Pohjanmaa': 'ca=4',
    'Pori': 'ca=10&w=110&m=187',
    'Satakunta': 'ca=10',
    'Lahti': 'ca=12&w=112&m=223',
    'Päijät-Häme': 'ca=12',
    'Hämeenlinna': 'ca=17&w=117&m=304',
    'Kanta-Häme': 'ca=17',
    'Kouvola': 'ca=20&w=120&m=345',
    'Kymenlaakso': 'ca=20',
    'Maarianhamina': 'ca=15&w=115&m=267',
    'Ahvenanmaa': 'ca=15',
}
LOCATION_OPTIONS_1 = {
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
    'Any': 'w=3',
}
LOCATION_OPTIONS_2 = {
    'Rovaniemi': 'ca=1&w=101&m=13',
    'Lappi': 'ca=1',
    'Kajaani': 'ca=3&w=103&m=57',
    'Kainuu': 'ca=3',
    'Joensuu': 'ca=9&w=109&m=157',
    'Pohjois-Karjala': 'ca=9',
    'Kuopio': 'ca=8&w=108&m=139',
    'Pohjois-Savo': 'ca=8',
    'Mikkeli': 'ca=13&w=113&m=235',
    'Etelä-Savo': 'ca=13',
}
LOCATION_OPTIONS_3 = {
    'Lappeenranta': 'ca=14&w=114&m=246',
    'Etelä-Karjala': 'ca=14',
    'Seinäjoki': 'ca=6&w=106&m=104',
    'Etelä-Pohjanmaa': 'ca=6',
    'Vaasa': 'ca=5&w=105&m=88',
    'Pohjanmaa': 'ca=5',
    'Kokkola': 'ca=4&w=104&m=69',
    'Keski-Pohjanmaa': 'ca=4',
    'Pori': 'ca=10&w=110&m=187',
    'Satakunta': 'ca=10',
}
LOCATION_OPTIONS_4 = {
    'Lahti': 'ca=12&w=112&m=223',
    'Päijät-Häme': 'ca=12',
    'Hämeenlinna': 'ca=17&w=117&m=304',
    'Kanta-Häme': 'ca=17',
    'Kouvola': 'ca=20&w=120&m=345',
    'Kymenlaakso': 'ca=20',
    'Maarianhamina': 'ca=15&w=115&m=267',
    'Ahvenanmaa': 'ca=15',
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

TRACKING_INTERVAL = 60 * 20  # 20 minutes
MAX_SAVED_LISTINGS = 60  # 60 listings saved per user
MAX_TRACKING_TIME = 60 * 60 * 24  # 24 hours
