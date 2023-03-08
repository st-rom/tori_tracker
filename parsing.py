import locale
import pytz
import re
import requests
import translators.server as tss

from bs4 import BeautifulSoup, NavigableString
from constants import *
from datetime import datetime, timedelta, timezone

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


def price_filter(goods, min_price=None, max_price=None):
    return [x for x in goods if (min_price is None or x['price'] > min_price) and
            (max_price is None or x['price'] < max_price)]


def list_announcements(location='Any', bid_type='Any', search_query='', category='Any', url=URL + 'li?', starting_ind=0,
                       page_num=1, goods=None, i=0, max_items=MAX_ITEMS_PER_SEARCH, min_price=None, max_price=None,
                       **kwargs):
    # print(starting_ind, page_num)
    # location_query = LOCATION_OPTIONS[location]
    location_query = '&'.join([LOCATION_OPTIONS[loc] for loc in location]) if type(location) == list else\
        LOCATION_OPTIONS[location]
    print('=99999=', 'st ind', starting_ind, 'i', i, 'page', page_num)
    if not goods:
        goods = []
    bid_type_query = BID_TYPES[bid_type]
    category_query = CATEGORIES[category]
    keyword_query = 'q=' + search_query.replace(' ', '+')
    page_num_query = 'o=' + str(page_num)
    # print('&'.join([url, location_query, bid_type_query, keyword_query, page_num_query]))
    r = requests.get('&'.join([url, location_query, bid_type_query, category_query, keyword_query, page_num_query]))
    print('&'.join([url, location_query, bid_type_query, category_query, keyword_query, page_num_query]))
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    # a list to store quotes
    list_of_goods = soup.find('div', class_='list_mode_thumb')
    if not list_of_goods:
        return i + starting_ind + MAX_ITEMS_ON_PAGE * (page_num - 1), goods
    list_of_goods = list_of_goods.findAll('a', attrs={'class': 'item_row_flex'})  # Add pages caller
    if not list_of_goods:
        return i + starting_ind + MAX_ITEMS_ON_PAGE * (page_num - 1), goods
    list_of_goods = list_of_goods[(starting_ind if starting_ind >= page_num * MAX_ITEMS_ON_PAGE else
                                   starting_ind % 40):]
    for listing in list_of_goods:
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
        listing_date = listing_date.replace(year=datetime.today().year)
        date_aware = tz.normalize(tz.localize(listing_date)).astimezone(pytz.utc)
        if date_aware > datetime.now(timezone.utc):
            date_aware = date_aware.replace(year=date_aware.year - 1)

        price = listing.find('p', class_='list_price ineuros').text.strip()
        price = int(price.split(' ')[0]) if price else 0
        img = listing.find('img', class_='item_image')
        product = {'title': listing.find('div', class_='li-title').text, 'date': date_aware, 'link': listing['href'],
                   'price': price, 'image': img['src'] if img else None}
        if (min_price is None or price >= min_price) and (max_price is None or price <= max_price):
            goods.append(product)
        i += 1
        if len(goods) >= max_items:
            return i + starting_ind + MAX_ITEMS_ON_PAGE * (page_num - 1), goods
    return list_announcements(location, bid_type, search_query, url=url, page_num=page_num+1,
                              starting_ind=0 if starting_ind < page_num * MAX_ITEMS_ON_PAGE else starting_ind % 40
                              if starting_ind < (page_num + 1) * MAX_ITEMS_ON_PAGE else starting_ind,
                              goods=goods, i=i, max_items=max_items, min_price=min_price, max_price=max_price, **kwargs)


def listing_info(url):
    # print(22222222222222, url)
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    listing = soup.find('div', class_='content')

    table_info = listing.find('table', class_='tech_data')
    print('SOLO', url)

    listing_date_str = string_cleaner(table_info.find('td', string='Ilmoitus jätetty:').findNext('td').text)
    str_split = listing_date_str.split(' ')
    if len(str_split) == 2:
        listing_date_str = listing_date_str.replace(TODAY, datetime.today().strftime('%d %Bta')) \
            .replace(YESTERDAY, (datetime.today() - timedelta(days=1)).strftime('%d %Bta'))
    else:
        listing_date_str = listing_date_str.replace(str_split[1], FIN_MON_ABBREVS.get(str_split[1], ''))
    tz = pytz.timezone('Europe/Helsinki')

    listing_date = datetime.strptime(listing_date_str, '%d %Bta %H:%M')
    listing_date = listing_date.replace(year=datetime.today().year)
    date_aware = tz.normalize(tz.localize(listing_date)).astimezone(pytz.utc)
    if date_aware > datetime.now(timezone.utc):
        date_aware = date_aware.replace(year=date_aware.year - 1)

    price = listing.find('div', class_='price').span
    price = price.text.strip() if price.string else price.span.text.strip()
    price = int(price.replace('€', '')) if price else None

    seller_info = string_retriever(listing.find('div', id='seller_info').div)
    descr = '\n'.join(string_retriever(listing.find('div', class_='body')))
    img = listing.find('img', id='main_image')['src']

    info = {'title': string_cleaner(listing.find('div', class_='topic').h1.text), 'date': date_aware,
            'link': url, 'price': price, 'location': seller_info, 'description': descr,
            'image': img if not img.endswith('.gif') else None}
    # print(info)
    return info


def beautify_items(items):
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    sep = '<brgr>'
    translations = tss.google(('\n' + sep + '\n').join([it['title'] for it in items]),
                              from_language='fi', to_language='en')
    translations = translations.split(sep)

    beautified = []
    print(translations)
    for i, item in enumerate(items):
        beautified.append('<b>Title</b>:\n{} (Fin.: {})\n<b>Price</b>: {}\n<b>Time added</b>: {}'.format(
            translations[i].strip(), item['title'], str(item['price']) + '€' if item['price'] else '-',
            item['date'].astimezone(pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b')))
    return beautified


def beautify_listing(item, trim=True):
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    sep = '. <brbr> '
    translations = tss.google(sep.join([item['title'], item['description']]), from_language='fi', to_language='en')
    # print(translations)
    translations = translations.split(sep)
    beautified = '<b>Title</b>:\n{} (Fin.: {})\n<b>Description</b> (eng):\n<i>{}</i>\n<b>Price</b>:' \
                 ' {}\n<b>Location</b>: {}\n<b>Time added</b>: {}\n'.format(
                  translations[0], item['title'], translations[-1], str(item['price']) + '€' if item['price'] else '-',
                  '/'.join(item['location']), item['date'].strftime('%H:%M, %d %b'))
    if trim:
        i = 0.9
        while len(beautified) >= 1024 and i >= 0:
            beautified = '<b>Title</b>:\n{} (Fin.: {})\n<b>Description</b> (eng):\n<i>{}</i>\n<b>Price</b>:' \
                         ' {}\n<b>Location</b>: {}\n<b>Time added</b>: {}\n'.format(
                          translations[0], item['title'], translations[-1][:int(len(translations[1])*i)],
                          str(item['price']) + '€' if item['price'] else '-', '/'.join(item['location']),
                          item['date'].astimezone(pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b'))
            i -= 0.1

    return beautified
