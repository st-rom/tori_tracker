import os
import urllib.parse as urlparse


from telegram.ext import ConversationHandler
from dotenv import load_dotenv


load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN' if os.getenv('USER') == 'roman' else 'BOT_TOKEN_PROD')
DB_URL = urlparse.urlparse(os.environ.get('DATABASE_URL' if os.getenv('USER') == 'roman' else 'DATABASE_URL_PROD'))

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
    'Any Location': 'w=3',
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
    'Any Location': 'w=3',
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
    'Any Location': 'w=3',
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
    'Any Location': 'w=3',
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
    'Any Location': 'w=3',
}

BID_TYPES = {
    'For Sale': 'st=s',
    'For Rent': 'st=u',
    'Wanted to Buy': 'st=k',
    'Wanted to Rent': 'st=h',
    'Free': 'st=g',
    'Any Type': 'st=s&st=g&st=u&st=k&st=h'
}

CATEGORIES = {
    'Vehicles and machines': 'cg=2000',
    'Apartments and properties': 'cg=1000',
    'Home and living': 'cg=3000',
    'Free time and hobbies': 'cg=4000',
    'Electronics': 'cg=5000',
    'Business and jobs': 'cg=6000',
    'Other': 'cg=7000',
    'Any Category': 'cg=0'
}

BID_TYPES_TRANSLATIONS = {
    'Myydään': 'For Sale',
    'Ostetaan': 'Wanted to Buy',
    'Vuokrataan': 'For Rent',
    'Halutaan vuokrata': 'Wanted to Rent',
    'Annetaan': 'Free',
}

# State definitions for top level conversation
SELECTING_ACTION, ADDING_LOCATION, ADDING_TYPE, ADDING_CATEGORY, ADDING_QUERY, ADDING_PRICE = map(chr, range(6))
# State definitions for second level conversation
SELECTING_LEVEL, SELECTING_FILTER = map(chr, range(4, 6))
# State definitions for descriptions conversation
SELECTING_FEATURE, TYPING, TYPING_STAY = map(chr, range(6, 9))
# Meta states
(STOPPING, SHOWING, CLEARING, CLEARING_PRICE, CLEARING_QUERY,
 HELP, DELETE_MESSAGE, SWITCH_LANG, UNSET_ALL, SHOW_SAVED) = map(chr, range(9, 19))

# Different constants for this example
(
    START_OVER,
    FEATURES,
    CURRENT_FEATURE,
    CURRENT_LEVEL,
    EXECUTE
) = map(chr, range(19, 24))

# Page numbers for locations
PAGE_1, PAGE_2, PAGE_3, PAGE_4 = map(chr, range(24, 28))

# Shortcut for ConversationHandler.END
END = ConversationHandler.END

LOCATION = 'locations'
TYPE_OF_LISTING = 'listing_types'
CATEGORY = 'category'
QUERY = 'search_term'
PRICE = 'price'
MIN_PRICE = 'min_price'
MAX_PRICE = 'max_price'

QUERY_LANGUAGE = 'query_language'

INSERT_USER_SQL = '''
    INSERT INTO users (id, username, first_name, last_name, last_login)
    VALUES ('{}', '{}', '{}', '{}', NOW())
    ON CONFLICT (id) DO UPDATE SET
    (username, first_name, last_name, last_login) = (EXCLUDED.username, EXCLUDED.first_name, EXCLUDED.last_name, NOW());
'''

INSERT_LISTING_SQL = '''
    INSERT INTO favourites (id, user_id, url, title, price, image_url, item_added, listing_type, is_deleted)
    VALUES ('{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', FALSE)
    ON CONFLICT (url) DO UPDATE SET
    (user_id, url, title, price, image_url, item_added, listing_type, is_deleted) = (EXCLUDED.user_id, EXCLUDED.url,
     EXCLUDED.title, EXCLUDED.price, EXCLUDED.image_url, EXCLUDED.item_added, EXCLUDED.listing_type, 
     EXCLUDED.is_deleted);
     SELECT url, title, price, image_url, item_added, listing_type, id FROM favourites 
     WHERE user_id = '{}' and is_deleted = FALSE;
'''

LIST_LISTING_SQL = '''
    SELECT url, title, price, image_url, item_added, listing_type, id FROM favourites 
    WHERE user_id = '{}' and is_deleted = FALSE;
'''

DELETE_LISTING_SQL = '''
    UPDATE favourites SET is_deleted = TRUE WHERE user_id = '{}' AND url = '{}';
    SELECT url, title, price, image_url, item_added, listing_type, id FROM favourites 
    WHERE user_id = '{}' and is_deleted = FALSE;
'''

DEFAULT_SETTINGS = {
    LOCATION: ['Tampere'],
    TYPE_OF_LISTING: ['For Sale', 'Free'],
    CATEGORY: 'Any Category',
}

ANY_SETTINGS = {
    LOCATION: ['Any Location'],
    TYPE_OF_LISTING: ['Any Type'],
    CATEGORY: 'Any Category',
}

QUERY_LANGUAGES = ['English', 'Finnish']

URL = 'https://www.tori.fi/'

BACK_BTN = 'Back to Menu \u21a9'
CONFIRM_BTN = 'Confirm \U0001F680'

MAX_ITEMS_PER_SEARCH = 5
MAX_ITEMS_ON_PAGE = 40

TRACKING_INTERVAL = 60 * 20  # 20 minutes
MAX_SAVED_LISTINGS = 60  # 60 listings saved per user
MAX_TRACKING_TIME = 60 * 60 * 48  # 48 hours
MSG_DESTRUCTION_TIMEOUT = 5  # 5 seconds
