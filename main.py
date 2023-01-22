import locale
import pytz
import re
import requests

from bs4 import BeautifulSoup, NavigableString
from datetime import datetime, timedelta
# sudo apt-get install language-pack-fi
# sudo dpkg-reconfigure locales  # NOT needed


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


def string_cleaner(string):
    return re.sub(r'\s\s+', ' ', string).strip()


def list_announcements(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html5lib')
    locale.setlocale(locale.LC_TIME, 'fi_FI.UTF-8')
    goods = []  # a list to store quotes
    list_of_goods = soup.find('div', class_='list_mode_thumb')
    for listing in list_of_goods.findAll('a', attrs={'class': 'item_row_flex'}):
        listing_date_str = string_cleaner(listing.find('div', class_='date_image').text)
        str_split = listing_date_str.split(' ')
        if len(str_split) == 2:
            listing_date_str = listing_date_str.replace(TODAY, datetime.today().strftime('%d %Bta'))\
                .replace(YESTERDAY, (datetime.today() - timedelta(days=1)).strftime('%d %Bta'))
        else:
            listing_date_str = listing_date_str.replace(str_split[0], FIN_MON_ABBREVS.get(str_split[0], ''))
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
        break
    print(goods)

def listing_info(url):
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
    price = price.text if price.string else price.span.text
    price = int(price.replace('€', '').strip()) if price else None

    seller_info = listing.find('div', id='seller_info').div
    seller_info = [string_cleaner(el) for el in seller_info.contents if isinstance(el, NavigableString) and not el.string.startswith('<') and string_cleaner(el.string)]
    info = {'title': string_cleaner(listing.find('div', class_='topic').h1.text), 'date': date_aware,
            'link': url, 'price': price, 'address': seller_info}
    print(info)


if __name__ == '__main__':
    url_tori = 'https://www.tori.fi/pirkanmaa?q=&cg=0&w=1&st=g&ca=11&l=0&md=th'  # &st=s
    url_product = 'https://www.tori.fi/pirkanmaa/Gubi_Multi_Lite_poytavalaisin_107682613.htm?ca=11&w=1'
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
    """
    # list_announcements(url_tori)
    listing_info(url_product)
