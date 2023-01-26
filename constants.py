import os

from dotenv import load_dotenv


load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')

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
    'Tampere': 'ca=11&m=210&w=111',
    'Pirkanmaa': 'ca=11&w=1',
    'Any': 'w=3'
}
BID_TYPES = {
    'Free': 'st=g',
    'Not free': 'st=s',
    'Any': 'st=s&st=g'
}

URL = 'https://www.tori.fi/'
