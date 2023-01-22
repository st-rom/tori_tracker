import locale
import logging
import os
import pytz
import re
import requests
import telegram as tg

from bs4 import BeautifulSoup, NavigableString
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler


load_dotenv()
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
    return re.sub(r'\s\s+', ' ', string.replace('\n', ' ')).strip()


def string_retriever(tag):
    """
    Retrieves only strings from the tag. Does not go deeper than base level
    :param tag:
    :return: list[str]
    """
    return [string_cleaner(str(el.string)) for el in tag.contents if isinstance(el, NavigableString)
            and not el.string.startswith('<') and string_cleaner(el.string)]

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

    seller_info = string_retriever(listing.find('div', id='seller_info').div)

    descr = '\n'.join(string_retriever(listing.find('div', class_='body')))
    info = {'title': string_cleaner(listing.find('div', class_='topic').h1.text), 'date': date_aware,
            'link': url, 'price': price, 'address': seller_info, 'description': descr,
            'image': listing.find('img', id='main_image')['src']}
    print(info)


# if __name__ == '__main__':
#     url_tori = 'https://www.tori.fi/pirkanmaa?q=&cg=0&w=1&st=g&ca=11&l=0&md=th'  # &st=s
#     url_product = 'https://www.tori.fi/pirkanmaa/Gubi_Multi_Lite_poytavalaisin_107682613.htm?ca=11&w=1'
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
    # listing_info(url_product)


BOT_TOKEN = os.environ.get('BOT_TOKEN')
#
#
#
# @bot.message_handler(commands=['start', 'hello'])
# def send_welcome(message):
#     bot.reply_to(message, "Howdy, how are you doing?")
#
#
# @bot.message_handler(func=lambda msg: True)
# def echo_all(message):
#     bot.reply_to(message, message.text)
#
#
# @dp.message_handler(commands=['start'])
# async def welcome(message: types.Message):
#     await message.answer('Hello! Please select your language.\nПривіт! Виберіть мову.', reply_markup = lang_kb)
#
# bot.infinity_polling()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: tg.Update, context: ContextTypes.DEFAULT_TYPE):
    print(context)
    user = update.message.from_user
    logger.info('Bot activated by user {} with id {}'.format(user['username'], user['id']))

    # Languages message
    msg = 'Hey! Please, choose a language:'

    # Languages menu
    languages_keyboard = [
        [tg.KeyboardButton('Suomi')],
        [tg.KeyboardButton('English')],
        [tg.KeyboardButton('Українська')]
    ]
    reply_kb_markup = tg.ReplyKeyboardMarkup(languages_keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg, reply_markup=reply_kb_markup)
    bot.message.reply_text('RETRO',
                         reply_markup=main_menu_keyboard())


def main_menu(bot, update):
  bot.callback_query.message.edit_text(main_menu_message(),
                          reply_markup=main_menu_keyboard())

def main_menu_keyboard():
  keyboard = [[InlineKeyboardButton('Menu 1', callback_data='m1')],
              [InlineKeyboardButton('Menu 2', callback_data='m2')],
              [InlineKeyboardButton('Menu 3', callback_data='m3')]]
  return InlineKeyboardMarkup(keyboard)


if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    application.run_polling()
