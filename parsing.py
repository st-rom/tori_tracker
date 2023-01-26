import locale
import pytz
import re
import requests
import translators.server as tss

from bs4 import BeautifulSoup, NavigableString
from constants import *
from datetime import datetime, timedelta

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


def list_announcements(location, bid_type, search_query, url=URL + 'li?', max_items=50, **kwargs):
    location = LOCATION_OPTIONS[location]
    bid_type = BID_TYPES[bid_type]
    search_query = 'q=' + search_query.replace(' ', '+')
    url = '&'.join([url, location, bid_type, search_query])
    # print(url)
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    goods = []  # a list to store quotes
    list_of_goods = soup.find('div', class_='list_mode_thumb')
    if not list_of_goods:
        return
    i = 0
    for listing in list_of_goods.findAll('a', attrs={'class': 'item_row_flex'}):
        listing_date_str = string_cleaner(listing.find('div', class_='date_image').text)
        str_split = listing_date_str.split(' ')
        # print(listing_date_str, '22')
        if len(str_split) == 2:
            listing_date_str = listing_date_str.replace(TODAY, datetime.today().strftime('%d %Bta'))\
                .replace(YESTERDAY, (datetime.today() - timedelta(days=1)).strftime('%d %Bta'))
        else:
            listing_date_str = listing_date_str.replace(str_split[1], FIN_MON_ABBREVS.get(str_split[1], ''))
            # print(listing_date_str)
        tz = pytz.timezone('Europe/Helsinki')

        listing_date = datetime.strptime(listing_date_str, '%d %Bta %H:%M')
        listing_date = listing_date\
            .replace(year=datetime.today().year if listing_date > datetime.now() else datetime.today().year - 1)
        date_aware = tz.normalize(tz.localize(listing_date)).astimezone(pytz.utc)
        price = listing.find('p', class_='list_price ineuros').text.strip()
        price = int(price.split(' ')[0]) if price else None
        product = {'title': listing.find('div', class_='li-title').text, 'date': date_aware, 'link': listing['href'],
                   'price': price}
        goods.append(product)
        i += 1
        if i >= max_items:
            break
    # print(goods)
    return goods


def listing_info(url):
    # print(22222222222222, url)
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    listing = soup.find('div', class_='content')

    table_info = listing.find('table', class_='tech_data')
    listing_date_str = string_cleaner(table_info.find('td', string='Ilmoitus jätetty:').findNext('td').text)
    tz = pytz.timezone('Europe/Helsinki')

    listing_date = datetime.strptime(listing_date_str, '%d %Bta %H:%M')
    listing_date = listing_date \
        .replace(year=datetime.today().year if listing_date > datetime.now() else datetime.today().year - 1)
    date_aware = tz.normalize(tz.localize(listing_date)).astimezone(pytz.utc)

    price = listing.find('div', class_='price').span
    price = price.text.strip() if price.string else price.span.text.strip()
    price = int(price.replace('€', '')) if price else None

    seller_info = string_retriever(listing.find('div', id='seller_info').div)

    descr = '\n'.join(string_retriever(listing.find('div', class_='body')))
    info = {'title': string_cleaner(listing.find('div', class_='topic').h1.text), 'date': date_aware,
            'link': url, 'price': price, 'location': seller_info, 'description': descr,
            'image': listing.find('img', id='main_image')['src']}
    # print(info)
    return info


def beautify_items(items):
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    sep = '<brbr>'
    translations = tss.google(('\n' + sep + '\n').join([it['title'] for it in items]),
                              from_language='fi', to_language='en')
    translations = translations.split(sep)

    beautified = []
    for i, item in enumerate(items):
        beautified.append('<b>Title</b>:\n{} (Fin.: {})\n<b>Price</b>: {}\n<b>Time added</b>: {}'.format(
            translations[i].strip(), item['title'], str(item['price']) + '€' if item['price'] else '-',
            item['date'].strftime('%H:%M, %d %b')))
    return beautified


def beautify_listing(item):
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    sep = '. <brbr> '
    translations = tss.google(sep.join([item['title'], item['description']]), from_language='fi', to_language='en')
    # print(translations)
    translations = translations.split(sep)
    beautified = '<b>Title</b>:\n{} (Fin.: {})\n<b>Description</b> (eng):\n<i>{}</i>\n<b>Price</b>:' \
                 ' {}\n<b>Location</b>: {}\n<b>Time added</b>: {}\n'.format(
                  translations[0], item['title'], translations[1], str(item['price']) + '€' if item['price'] else '-',
                  '/'.join(item['location']), item['date'].strftime('%H:%M, %d %b'))
    i = 0.9
    while len(beautified) >= 1024 and i >= 0:
        beautified = '<b>Title</b>:\n{} (Fin.: {})\n<b>Description</b> (eng):\n<i>{}</i>\n<b>Price</b>:' \
                     ' {}\n<b>Location</b>: {}\n<b>Time added</b>: {}\n'.format(
                      translations[0], item['title'], translations[1][:int(len(translations[1])*i)],
                      str(item['price']) + '€' if item['price'] else '-', '/'.join(item['location']),
                      item['date'].strftime('%H:%M, %d %b'))
        i -= 0.1

    return beautified
