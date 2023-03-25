import locale
import logging
import psycopg2
import pytz
import re
import requests
import translators.server as tss
import uuid

from bs4 import BeautifulSoup, NavigableString
from constants import *
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from logtail import LogtailHandler

"""
ca is region code where ca=11 is Pirkanmaa (Tampere region)
q is query (keyword)
cg is category where cg=0 is any
o is page number
st is listing type where:
=s - for sale
=k - want to buy
=u - for rent
=h - want to rent
=g - give for free
md = th ?
l = 0 ?
w = 1 ?
c = 0 ?
w=111&m=210  - Tampere?
pe=3 - price max (3 means third option)
What is w??
"""


load_dotenv()
handler = LogtailHandler(source_token=os.environ.get('LOGTAIL_TOKEN'))
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
if os.getenv('USER') != 'roman':
    logger.addHandler(handler)


def generate_unique_job_name(jobs):
    """
    Generates unique job name
    """
    job_name = str(uuid.uuid4())
    current_jobs = [job.name for job in jobs]
    while job_name in current_jobs:
        job_name = str(uuid.uuid4())
    return job_name


def remove_job_if_exists(name, context) -> bool:  # unused
    """
    Remove job with given name. Returns whether job was removed.
    """
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def params_beautifier(params):
    nice_str = ''
    for k in params.keys():
        val_str = ', '.join(params.get(k)) if type(params.get(k)) == list else str(params.get(k))
        nice_str += ' '.join(k.capitalize().split('_')) + ': ' + val_str + '\n'
    return nice_str.strip()


def string_cleaner(string):
    return re.sub(r'\s\s+', ' ', string.replace('\n', ' ')).strip()



def string_retriever(tag):
    """
    Retrieves only strings from the tag. Does not go deeper than base level
    :param tag:
    :return: list[str]
    """
    return [string_cleaner(str(el.string)) for el in tag.contents if isinstance(el, NavigableString)
            and not el.string.startswith('<') and string_cleaner(el.string)]


def price_filter(goods, min_price=None, max_price=None):
    return [x for x in goods if (min_price is None or x['price'] > min_price) and
            (max_price is None or x['price'] < max_price)]


def list_announcements(locations=ANY_SETTINGS[LOCATION], listing_types=ANY_SETTINGS[TYPE_OF_LISTING], search_term='',
                       category=ANY_SETTINGS[CATEGORY], url=URL + 'li?', goods=None, max_items=MAX_ITEMS_PER_SEARCH,
                       min_price=None, max_price=None, starting_ind=0, ignore_logs=False, **kwargs):
    location_query = '&'.join([LOCATION_OPTIONS[loc] for loc in locations])
    if not goods:
        goods = []
    bid_type_query = '&'.join([BID_TYPES[t] for t in listing_types])
    category_query = CATEGORIES[category]
    keyword_query = 'q=' + search_term.replace(' ', '+')
    page_num = starting_ind // MAX_ITEMS_ON_PAGE + 1
    page_num_query = 'o=' + str(page_num)
    # if True:
    #     logger.info('Starting index: {}, page number: {}'.format(starting_ind, page_num))
    r = requests.get('&'.join([url, location_query, bid_type_query, category_query, keyword_query, page_num_query]))
    if not starting_ind and not ignore_logs:
        logger.info('Search url: {}'.format('&'.join([url, location_query, bid_type_query,
                                                      category_query, keyword_query, page_num_query])))
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    # a list to store quotes
    list_of_goods = soup.find('div', class_='list_mode_thumb')
    if not list_of_goods:
        return starting_ind, goods
    list_of_goods = list_of_goods.findAll('a', attrs={'class': 'item_row_flex'})  # Add pages caller
    if not list_of_goods:
        return starting_ind, goods
    list_of_goods = list_of_goods[starting_ind % MAX_ITEMS_ON_PAGE:]
    if not list_of_goods:
        return starting_ind, goods
    for listing in list_of_goods:
        listing_date_str = string_cleaner(listing.find('div', class_='date_image').text)
        str_split = listing_date_str.split(' ')
        if len(str_split) == 2:
            listing_date_str = listing_date_str.replace(TODAY, datetime.today().strftime('%d %Bta'))\
                .replace(YESTERDAY, (datetime.today() - timedelta(days=1)).strftime('%d %Bta'))
        else:
            listing_date_str = listing_date_str.replace(str_split[1], FIN_MON_ABBREVS.get(str_split[1], str_split[1]))
        tz = pytz.timezone('Europe/Helsinki')

        listing_date = datetime.strptime(listing_date_str, '%d %Bta %H:%M')
        listing_date = listing_date.replace(year=datetime.today().year)
        date_aware = tz.normalize(tz.localize(listing_date)).astimezone(pytz.utc)
        if date_aware > datetime.now(timezone.utc):
            date_aware = date_aware.replace(year=date_aware.year - 1)

        price = listing.find('p', class_='list_price ineuros').text.strip()
        if price:
            price = price[:price.find('€')].split(' ')
            price = int(''.join([p for p in price if p.isnumeric()]))
        else:
            price = 0

        bid_type_str = 'Unknown'
        children = listing.find('div', class_='cat_geo').findChildren(recursive=False)
        for child in children:
            if child.text and child.text.strip() in BID_TYPES_TRANSLATIONS:
                bid_type_str = BID_TYPES_TRANSLATIONS[child.text.strip()]
                break
        if bid_type_str == 'Unknown':
            logger.warning('Unexpected behavior. Could not get a type of {}'.format(listing['href']))

        img = listing.find('img', class_='item_image')
        product = {'title': listing.find('div', class_='li-title').text, 'link': listing['href'].replace('\xa0', '+'),
                   'date': date_aware, 'price': price, 'image': img['src'].replace('\xa0', '+') if img else None,
                   'uid': str(uuid.uuid4()), 'bid_type': bid_type_str}
        if (min_price is None or price >= min_price) and (max_price is None or price <= max_price):
            goods.append(product)
        starting_ind += 1
        if len(goods) >= max_items:
            return starting_ind, goods
    return list_announcements(locations=locations, listing_types=listing_types, search_term=search_term,
                              category=category, url=url, ignore_logs=True, starting_ind=starting_ind,
                              goods=goods, max_items=max_items, min_price=min_price, max_price=max_price, **kwargs)


def listing_info(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    listing = soup.find('div', class_='content')
    if not listing:
        return url
    table_info = listing.find('table', class_='tech_data')
    if not table_info:
        return 'Selected listing is no longer available.'
    listing_date_str = string_cleaner(table_info.find('td', string='Ilmoitus jätetty:').findNext('td').text)
    str_split = listing_date_str.split(' ')
    if len(str_split) == 2:
        listing_date_str = listing_date_str.replace(TODAY, datetime.today().strftime('%d %Bta')) \
            .replace(YESTERDAY, (datetime.today() - timedelta(days=1)).strftime('%d %Bta'))
    else:
        listing_date_str = listing_date_str.replace(str_split[1], FIN_MON_ABBREVS.get(str_split[1], str_split[1]))
    tz = pytz.timezone('Europe/Helsinki')
    listing_date = datetime.strptime(listing_date_str, '%d %Bta %H:%M')
    listing_date = listing_date.replace(year=datetime.today().year)
    date_aware = tz.normalize(tz.localize(listing_date)).astimezone(pytz.utc)
    if date_aware > datetime.now(timezone.utc):
        date_aware = date_aware.replace(year=date_aware.year - 1)

    bid_type_el = table_info.find('td', string='Ilmoitustyyppi:')
    if bid_type_el:
        bid_type_str = BID_TYPES_TRANSLATIONS[string_cleaner(bid_type_el.findNext('td').text)]
    else:
        bid_type_str = None

    price = listing.find('div', class_='price').span
    price = price.text.strip() if price.string else price.span.text.strip()
    price = price.replace('–', '')
    if price:
        price = price[:price.find('€')].split(' ')
        price = int(''.join([p for p in price if p.isnumeric()]))
    else:
        price = 0

    seller_info = string_retriever(listing.find('div', id='seller_info').div)
    descr = '\n'.join(string_retriever(listing.find('div', class_='body')))
    img = listing.find('img', id='main_image')['src']

    info = {'title': string_cleaner(listing.find('div', class_='topic').h1.text), 'date': date_aware,
            'link': url.replace('\xa0', '+'), 'price': price, 'location': seller_info, 'description': descr,
            'image': img.replace('\xa0', '+') if not img.endswith('.gif') else None, 'bid_type': bid_type_str}
    return info


def beautify_items(items, lang='en'):
    if lang == 'fi':  # TODO: future language settings
        lang = 'en'
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    sep = '<brgr>'
    translations = tss.google(('\n' + sep + '\n').join([it['title'] for it in items]),
                              from_language='fi', to_language=lang)
    translations = translations.split(sep)

    beautified = []
    for i, item in enumerate(items):
        beautified.append('<b><i>{} (Fin.: {})</i></b>\n<b>Price</b>: {}\n<b>Listing type</b>: {}\n<b>Time added</b>:'
                          ' {}'.format(translations[i].strip(), item['title'], str(item['price']) + '€'
                                       if item['price'] else '-', item['bid_type'],
                                       item['date'].astimezone(pytz.timezone('Europe/Helsinki')).strftime(
                                           '%H:%M, %d %b')))
    return beautified


def beautify_listing(item, trim=True, lang='en'):
    if lang == 'fi':
        lang = 'en'
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    sep = '<brgr>'
    translations = tss.google(('\n' + sep + '\n').join([item['title'], item['description']]),
                              from_language='fi', to_language=lang)
    translations = translations.split(sep)
    bid_type_str = '<b>Listing type</b>: {}\n'.format(item['bid_type']) if item['bid_type'] else ''
    beautified = '<b><i>{} (Fin.: {})</i></b>\n<b>Description</b> (eng):\n<i>{}</i>\n<b>Price</b>: {}\n' \
                 '<b>Location</b>: {}\n{}<b>Time added</b>: {}\n' \
                 '<a href="{}">Original post</a>'.format(
                  translations[0].strip(), item['title'], translations[-1].strip(),
                  str(item['price']) + '€' if item['price'] else '-', '/'.join(item['location']), bid_type_str,
                  item['date'].astimezone(pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b'), item['link'])
    if trim:
        i = 0.95
        while len(beautified) >= 1024 and i >= 0:
            beautified = '<b><i>{} (Fin.: {})</i></b>\n<b>Description</b> (eng):\n<i>{}</i>\n<b>Price</b>:' \
                         ' {}\n<b>Location</b>: {}\n{}<b>Time added</b>: {}\n<a href="{}">' \
                         'Original post</a>'.format(
                          translations[0].strip(), item['title'],
                          translations[-1][:int(len(translations[1])*i)].strip() + '...',
                          str(item['price']) + '€' if item['price'] else '-', '/'.join(item['location']), bid_type_str,
                          item['date'].astimezone(pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b'),
                          item['link'])
            i -= 0.05

    return beautified


def parse_psql_listings(data):
    listings = []
    for listing in data:
        listings.append({'title': listing[1], 'link': listing[0], 'date': listing[4], 'price': listing[2],
                         'image': listing[3], 'bid_type': listing[5], 'uid': listing[6]})
    return listings


def get_saved_from_db(user_id, saved_listings):
    """
    Retrieve Saved listings from db
    """
    result = saved_listings
    if not result:
        conn = psycopg2.connect(database=DB_URL.path[1:],
                                host=DB_URL.hostname,
                                user=DB_URL.username,
                                password=DB_URL.password,
                                port=DB_URL.port)
        cur = conn.cursor()
        cur.execute(
            LIST_LISTING_SQL.format(user_id))
        data = cur.fetchall()
        conn.commit()
        cur.close()
        conn.close()
        result = parse_psql_listings(data)
    return result
