import copy
import inspect
import locale
import logging
import sys
import psycopg2
import pytz
import translators.server as tss
import urllib.parse as urlparse
import uuid

from constants import *
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from logtail import LogtailHandler
from parsing import beautify_items, list_announcements, listing_info, beautify_listing, params_beautifier
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand, error,
                      ReplyKeyboardRemove)
from telegram.ext import (Application, CallbackQueryHandler, ContextTypes, ConversationHandler,
                          CommandHandler, MessageHandler, filters)
from telegram.warnings import PTBUserWarning
from warnings import filterwarnings


load_dotenv()
handler = LogtailHandler(source_token=os.environ.get('LOGTAIL_TOKEN'))
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
if os.getenv('USER') != 'roman':
    logger.addHandler(handler)

# State definitions for top level conversation
SELECTING_ACTION, ADDING_LOCATION, ADDING_TYPE, ADDING_CATEGORY, ADDING_QUERY, ADDING_PRICE = map(chr, range(6))
# State definitions for second level conversation
SELECTING_LEVEL, SELECTING_FILTER = map(chr, range(4, 6))
# State definitions for descriptions conversation
SELECTING_FEATURE, TYPING, TYPING_STAY = map(chr, range(6, 9))
# Meta states
STOPPING, SHOWING, CLEARING, CLEARING_PRICE, CLEARING_QUERY, HELP, DELETE_MESSAGE = map(chr, range(9, 16))

# Different constants for this example
(
    START_OVER,
    FEATURES,
    CURRENT_FEATURE,
    CURRENT_LEVEL,
) = map(chr, range(16, 20))

# Page numbers for locations
PAGE_1, PAGE_2, PAGE_3, PAGE_4 = map(chr, range(20, 24))

# Shortcut for ConversationHandler.END
END = ConversationHandler.END
BACK = 'Back to menu \u21a9'

LOCATION = 'location'
TYPE_OF_LISTING = 'listing_type'
CATEGORY = 'category'
QUERY = 'search_terms'
PRICE = 'price'
MIN_PRICE = 'min_price'
MAX_PRICE = 'max_price'

DEFAULT_SETTINGS = {
    LOCATION: 'Any',
    TYPE_OF_LISTING: 'Any',
    CATEGORY: 'Any',
}
# DEFAULT_SETTINGS = {
#     LOCATION: 'Pirkanmaa',
#     TYPE_OF_LISTING: 'Any',
#     CATEGORY: 'Electronics',
#     QUERY: 'guitar'
# }

INSERT_SQL = '''
    INSERT INTO users (id, username, first_name, last_name, last_login)
    VALUES ('{}', '{}', '{}', '{}', NOW())
    ON CONFLICT (id) DO UPDATE SET
    (username, first_name, last_name, last_login) = (EXCLUDED.username, EXCLUDED.first_name, EXCLUDED.last_name, NOW());
'''

DB_URL = urlparse.urlparse(os.environ.get('DATABASE_URL' if os.getenv('USER') == 'roman' else 'DATABASE_URL_PROD'))


def log_and_update(log=False, db_update=True):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            update = None
            user = None
            if isinstance(args[0], Update):
                update = args[0]
                user = update.message.from_user if update.message else update.callback_query.from_user
            if log and update:
                txt = 'Function {} executed by user_id=`{}`'.format(func.__name__, user.id)
                if user.username:
                    txt += ', username=`@{}`'.format(user.username)
                if user.first_name or user.last_name:
                    if user.first_name:
                        txt += ', first_name=`{}`'.format(user.first_name)
                    if user.last_name:
                        txt += ', last_name=`{}`'.format(user.last_name)
                logger.info(txt)
            result = await func(*args, **kwargs)  # logging before execution, but saving after it
            if db_update and update:
                conn = psycopg2.connect(database=DB_URL.path[1:],
                                        host=DB_URL.hostname,
                                        user=DB_URL.username,
                                        password=DB_URL.password,
                                        port=DB_URL.port)
                cur = conn.cursor()
                cur.execute(INSERT_SQL.format(user.id, user.username or '', user.first_name or '',
                                              user.last_name or ''))
                conn.commit()
                cur.close()
                conn.close()
            return result
        return wrapper
    return decorator


def error_handler(type_, value, tb):
    sys.__excepthook__(type_, value, tb)
    logger.exception('Uncaught exception: {0}'.format(str(value)))


# Install exception handler
sys.excepthook = error_handler


async def set_default_commands(bot) -> None:
    """
    Sets up default commands
    Stopped using because it was not properly updating on mobile
    """
    await bot.delete_my_commands()
    # set commands
    command = [BotCommand('start', 'to start the bot'),
               BotCommand('search', 'to search for newly available items'),
               BotCommand('set_tracker', 'to set up monitoring for a particular search'),
               BotCommand('help', 'to show a help message'),
               ]
    await bot.set_my_commands(command)  # rules-bot


async def set_extended_commands(bot) -> None:
    """
    Sets up more commands
    """
    await bot.delete_my_commands()
    # set commands
    command = [BotCommand('start', 'to start the bot'),
               BotCommand('search', 'to search for newly available items'),
               BotCommand('set_tracker', 'to set up monitoring for a particular search'),
               BotCommand('help', 'to show a help message'),
               BotCommand('list_trackers', 'to list all active trackers'),
               BotCommand('unset_tracker', 'to unset a specific tracker'),
               BotCommand('unset_all', 'to cancel all ongoing trackers'),
               ]
    await bot.set_my_commands(command)  # rules-bot


async def post_init(application: Application) -> None:
    bot = application.bot
    await set_extended_commands(bot)


@log_and_update()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_text = 'Bot activated by user with id {}'.format(user.id)
    if user.username:
        user_text += '\n Username: `@{}`'.format(user.username)
    if user.first_name or user.last_name:
        user_text += '\n'
        if user.first_name:
            user_text += ' First name: `{}`'.format(user.first_name)
        if user.last_name:
            user_text += ' Last name: `{}`'.format(user.last_name)
    logger.info(user_text)

    msg = 'Hei \U0001f44b\nWelcome to Tori Tracker - an unofficial bot for the largest online marketplace' \
          ' in Finland!\nHere you can quickly get the list of the latest available items on tori.fi' \
          ' and set up a tracker for particular items you are interested in.\nTo get started, select one of the' \
          ' following commands:\n\t• /search - to search for newly available items\n\t• /set_tracker - to set up' \
          ' monitoring for particular listings\nUse /help if you need more information.'
    msg = msg.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    reply_markup = ReplyKeyboardRemove()
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg, reply_markup=reply_markup)


@log_and_update(log=True)
async def help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info('Might need help.')

    msg = '\ud83d\udd27 ' \
          'This bot can search for available listings or track newly added items on tori.fi - the largest marketplace' \
          ' for second-hand goods in Finland.\nUse /search to search ' \
          'and set up the filters for your search of the latest listings on Tori.\nUse /set_tracker when setting up ' \
          'a tracker for the item you wish to find. You will receive a message as soon as a listing that matches your' \
          ' parameters is added to Tori.\nIn case you confront an issue, please message' \
          ' me \ud83d\udc47\n\n\U0001f468\u200D\U0001f527 Telegram: @stroman\n\u2709 Email: rom.stepaniuk@gmail.com'
    msg = msg.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg)


# Top level conversation callbacks
@log_and_update(db_update=False)
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Starts the search conversation and asks the user about their location.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    # cur.execute(insert_sql.format(user.id, user.username, user.first_name, user.last_name))
    text = 'Choose the filters you wish to apply for the search.'
    if not context.user_data.get(FEATURES):
        context.user_data[FEATURES] = copy.deepcopy(DEFAULT_SETTINGS)

    buttons = [
        [
            InlineKeyboardButton(text='Search terms \ud83d\udd24', callback_data=str(ADDING_QUERY)),
            InlineKeyboardButton(text='Location \ud83c\udf04', callback_data=str(ADDING_LOCATION)),
        ],
        [
            InlineKeyboardButton(text='Listing type \ud83c\udf81', callback_data=str(ADDING_TYPE)),
            InlineKeyboardButton(text='Price range \ud83d\udcb0', callback_data=str(ADDING_PRICE)),
        ],
        [
            InlineKeyboardButton(text='Category \ud83c\udfbe', callback_data=str(ADDING_CATEGORY)),
            InlineKeyboardButton(text='Help \u2753', callback_data=str(HELP)),
        ],
        [
            InlineKeyboardButton(text='Clear filters \u274c', callback_data=str(CLEARING)),
            # InlineKeyboardButton(text='Show filters \ud83d\udc40', callback_data=str(SHOWING)),
        ],
        [
            InlineKeyboardButton(text='Search \ud83d\udd0e', callback_data=str(END)),
        ],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # If we're starting over we don't need to send a new message
    if context.user_data[FEATURES] != DEFAULT_SETTINGS:
        text += '\n\n\u2757 Current filters:\n{}\n\nPress `Clear filters \u274c` to reset them.'.format(
                  params_beautifier(context.user_data[FEATURES]))
    text += '\nPress `Search \ud83d\udd0e` when you are ready to proceed.'
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    if context.user_data.get(START_OVER) and update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    elif context.user_data.get(START_OVER):
        await update.message.reply_text(
            "Selection saved successfully! Let's see what's available on Tori right now!"
        )
        await update.message.reply_text(text=text, reply_markup=keyboard)
    else:
        logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
        if update.message.text == '/set_tracker':
            intro = 'Set up a tracker for the items you are looking for. As soon as new one will appear you will get' \
                   ' a notification.'
        else:
            intro = 'Set up filters for the desired search and find the items you need.'
        await update.message.reply_text(intro)
        await update.message.reply_text(text=text, reply_markup=keyboard)

    context.user_data[START_OVER] = False
    return SELECTING_ACTION


@log_and_update(log=True, db_update=False)
async def adding_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_1.keys()), 2)),
        [InlineKeyboardButton(text=BACK, callback_data=END),
         InlineKeyboardButton(text='Next \u27a1', callback_data=PAGE_2)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    loc_val = ud[FEATURES].get(LOCATION)
    loc_str = ', '.join(loc_val) if type(loc_val) == list else loc_val
    text = 'Choose out of the following locations.\n' \
           'Current selections: {}\n' \
           'Press `Next \u27a1` to see more options.\n' \
           'When you are done, press `{}`'.format(loc_str, BACK)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one. ' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    context.user_data[START_OVER] = False

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


async def adding_location_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_2.keys()), 2)),
        [InlineKeyboardButton(text='Previous \u2b05', callback_data=PAGE_1),
         InlineKeyboardButton(text=BACK, callback_data=END),
         InlineKeyboardButton(text='Next \u27a1', callback_data=PAGE_3)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    loc_val = ud[FEATURES].get(LOCATION)
    loc_str = ', '.join(loc_val) if type(loc_val) == list else loc_val
    text = 'Choose out of the following locations.\n' \
           'Current selections: {}\n' \
           'Press `Next \u27a1` to see more options.\n' \
           'When you are done, press `{}`'.format(loc_str, BACK)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one. ' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    context.user_data[START_OVER] = False

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


async def adding_location_3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_3.keys()), 2)),
        [InlineKeyboardButton(text='Previous \u2b05', callback_data=PAGE_2),
         InlineKeyboardButton(text=BACK, callback_data=END),
         InlineKeyboardButton(text='Next \u27a1', callback_data=PAGE_4)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    loc_val = ud[FEATURES].get(LOCATION)
    loc_str = ', '.join(loc_val) if type(loc_val) == list else loc_val
    text = 'Choose out of the following locations.\n' \
           'Current selections: {}\n' \
           'Press `Next \u27a1` to see more options.\n' \
           'When you are done, press `{}`'.format(loc_str, BACK)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one. ' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    context.user_data[START_OVER] = False

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


async def adding_location_4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_4.keys()), 2)),
        [InlineKeyboardButton(text='Previous \u2b05', callback_data=PAGE_3),
         InlineKeyboardButton(text=BACK, callback_data=END)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    loc_val = ud[FEATURES].get(LOCATION)
    loc_str = ', '.join(loc_val) if type(loc_val) == list else loc_val
    text = 'Choose out of the following locations.\n' \
           'Current selections: {}\n' \
           'Press `Previous \u2b05` to see previous options.\n' \
           'When you are done, press `{}`'.format(loc_str, BACK)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one. ' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    context.user_data[START_OVER] = False

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


@log_and_update(log=True, db_update=False)
async def adding_bid_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected bid type
    """
    context.user_data[CURRENT_FEATURE] = TYPE_OF_LISTING
    ud = context.user_data
    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k == ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(BID_TYPES.keys()), 2)),
        [InlineKeyboardButton(text=BACK, callback_data=END)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    text = 'Choose one of the following types:'
    if ud[FEATURES].get(ud[CURRENT_FEATURE]):
        text = "Current selection: `{}`\n" \
               "To change it, select one of the following:".format(ud[FEATURES][ud[CURRENT_FEATURE]])
    context.user_data[START_OVER] = False

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


@log_and_update(log=True, db_update=False)
async def adding_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected category
    """
    context.user_data[CURRENT_FEATURE] = CATEGORY
    ud = context.user_data
    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k == ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(CATEGORIES.keys()), 2)),
        [InlineKeyboardButton(text=BACK, callback_data=END)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    text = 'Choose one of the following categories:'
    if ud[FEATURES].get(ud[CURRENT_FEATURE]):
        text = "Current selection: `{}`\n" \
               "To change it, select one of the following:".format(ud[FEATURES][ud[CURRENT_FEATURE]])
    context.user_data[START_OVER] = False

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


@log_and_update(log=True, db_update=False)
async def adding_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for keywords feature.
    """
    context.user_data[CURRENT_FEATURE] = QUERY
    text = 'Enter the keywords (e.g., guitar, couch, ice skates)'
    buttons = [
        [InlineKeyboardButton(text=BACK, callback_data=END)]
    ]

    if context.user_data[FEATURES].get(QUERY):
        buttons.insert(0, [InlineKeyboardButton(text='Clear this filter \u274c', callback_data=CLEARING_QUERY)])
        text += '\nCurrent search keywords: `{}`'.format(context.user_data[FEATURES].get(QUERY))

    buttons = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons)

    return TYPING


@log_and_update(log=True, db_update=False)
async def clear_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Clear query filters and return to feature selection.
    """
    context.user_data[FEATURES].pop(QUERY, None)
    context.user_data[START_OVER] = True

    return await adding_query(update, context)


@log_and_update(db_update=False)
async def adding_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected price limitations
    """
    ud = context.user_data
    buttons = [[
            InlineKeyboardButton(text='Set up min, €', callback_data=MIN_PRICE),
            InlineKeyboardButton(text='Set up max, €', callback_data=MAX_PRICE),
    ],
        [InlineKeyboardButton(text=BACK, callback_data=END)]
    ]
    # pr/int(buttons)
    text = 'Set up price filters.'
    if ud[FEATURES].get(MIN_PRICE) or ud[FEATURES].get(MAX_PRICE):
        text = 'Current price filters:\n'
        buttons.insert(1, [InlineKeyboardButton(text='Clear price filters \u274c', callback_data=CLEARING_PRICE)])
        if ud[FEATURES].get(MIN_PRICE):
            text += 'Min price: {}€\n'.format(ud[FEATURES].get(MIN_PRICE))
        if ud[FEATURES].get(MAX_PRICE):
            text += 'Max price: {}€\n'.format(ud[FEATURES].get(MAX_PRICE))
        text += 'You can edit or clear your current price settings.'

    keyboard = InlineKeyboardMarkup(buttons)
    call_func = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    if update.callback_query:
        await update.callback_query.answer()
    if ud[FEATURES].get(TYPE_OF_LISTING) == 'Free':
        await call_func(text='Price settings do not work with `Free` listing type filter.',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]]))
    else:
        await call_func(text=text, reply_markup=keyboard)
    return SELECTING_FILTER


@log_and_update(log=True, db_update=False)
async def set_min_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for min price.
    """
    context.user_data[CURRENT_FEATURE] = MIN_PRICE
    text = "Okay, tell me min price, €"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons)
    return TYPING_STAY


@log_and_update(log=True, db_update=False)
async def set_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for max price.
    """
    context.user_data[CURRENT_FEATURE] = MAX_PRICE
    text = "Okay, tell me max price, €"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons)
    return TYPING_STAY


@log_and_update(log=True, db_update=False)
async def clear_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Clear price filters and return to feature selection.
    """
    context.user_data[FEATURES].pop(MIN_PRICE, None)
    context.user_data[FEATURES].pop(MAX_PRICE, None)
    context.user_data[START_OVER] = True

    return await adding_price(update, context)


async def end_selecting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    End gathering of features and return to parent conversation.
    """
    context.user_data[START_OVER] = True
    await search(update, context)
    return END


async def save_selection_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Save multiple inputs for feature and return to feature selection.
    """
    user_data = context.user_data
    await update.callback_query.answer()
    if user_data[FEATURES].get(user_data[CURRENT_FEATURE]) == 'Any':
        user_data[FEATURES].pop(user_data[CURRENT_FEATURE])
    if user_data[FEATURES].get(user_data[CURRENT_FEATURE]):
        if update.callback_query.data == 'Any':
            user_data[FEATURES][user_data[CURRENT_FEATURE]] = update.callback_query.data
        elif update.callback_query.data not in user_data[FEATURES][user_data[CURRENT_FEATURE]]:
            user_data[FEATURES][user_data[CURRENT_FEATURE]].append(update.callback_query.data)
        else:
            user_data[FEATURES][user_data[CURRENT_FEATURE]].remove(update.callback_query.data)
    else:
        user_data[FEATURES][user_data[CURRENT_FEATURE]] = [update.callback_query.data]

    user_data[START_OVER] = True
    #  {'\x0b': {'\x01': ['Pirkanmaa'], 'Pirkanmaa': ['Tampere']}, '\n': True, '\x0c': 'Tampere'}
    if update.callback_query.data in LOCATION_OPTIONS_1:
        return await adding_location(update, context)
    elif update.callback_query.data in LOCATION_OPTIONS_2:
        return await adding_location_2(update, context)
    elif update.callback_query.data in LOCATION_OPTIONS_3:
        return await adding_location_3(update, context)
    else:
        return await adding_location_4(update, context)


async def save_selection_single(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Save input for feature and return to feature selection.
    """
    user_data = context.user_data
    await update.callback_query.answer()
    user_data[FEATURES][user_data[CURRENT_FEATURE]] = update.callback_query.data
    if user_data[CURRENT_FEATURE] == TYPE_OF_LISTING and update.callback_query.data == 'Free':
        context.user_data[FEATURES].pop(MIN_PRICE, None)
        context.user_data[FEATURES].pop(MAX_PRICE, None)

    user_data[START_OVER] = True
    return await end_selecting(update, context)


async def save_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Save input for feature and return to feature selection.
    """
    user_data = context.user_data
    user_data[FEATURES][user_data[CURRENT_FEATURE]] = update.message.text
    user_data[START_OVER] = True

    return await end_selecting(update, context)


async def save_input_stay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Save input for feature and stay at feature modifier.
    """
    user_data = context.user_data
    try:
        val = int(update.message.text)
        if val >= 0:
            user_data[FEATURES][user_data[CURRENT_FEATURE]] = val
        else:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "\u2757\u2757 Incorrect input format \u2757\u2757"
        )
    user_data[START_OVER] = True

    return await adding_price(update, context)


@log_and_update(log=True, db_update=False)
async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Clear all filters and return to feature selection.
    """
    context.user_data[FEATURES] = copy.deepcopy(DEFAULT_SETTINGS)
    context.user_data[START_OVER] = True
    return await search(update, context)


@log_and_update(log=True, db_update=False)
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Shows help text
    """
    logger.info('Might need help.')
    await update.callback_query.edit_message_text(text=(
        "To search for the desired item, you can set up the following search filters:\n"
        "• Search terms \ud83d\udd24 - add a search phrase in English to find exactly what you need (e.g., chair,"
        " fridge, guitar)\n"
        "• Location \ud83c\udf04 - choose the city or the region where you want to find the item\n"
        "• Listing type \ud83c\udf81 - you can filter by Free items, Renting or Regular items\n"
        "• Price range \ud83d\udcb0 - set up Min and Max ranges of prices\n"
        "• Category \ud83c\udfbe - choose a category of the items (e.g., cars, hobby, furniture)\n"
        "• Help \u2753 - get a message with the description of all buttons\n"
        "• Clear filters \u274c - clears all of the previously selected filters (resets to defaults)\n"
        # "• Show filters \ud83d\udc40 - shows you ALL filters that you've previously set up\n"
        "• Search \ud83d\udd0e - press this button to start the search\n"
        "For other useful information use /help").encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE'),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]])
    )
    context.user_data[START_OVER] = True

    return SHOWING


@log_and_update()
async def start_searching(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    End conversation and start the search.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    search_params = copy.deepcopy(context.user_data.get(FEATURES, DEFAULT_SETTINGS))
    beautiful_params = params_beautifier(search_params)
    chat_id = update.effective_chat.id
    query = update.callback_query
    try:
        await query.answer()
        if query.data.endswith('show_more'):
            await update.callback_query.edit_message_text(text='Showing more listings:')
            starting_ind = int(query.data.split('_')[0])
            search_params['ignore_logs'] = True
        else:
            starting_ind = 0
            search_params['ignore_logs'] = False
    except AttributeError as e:
        starting_ind = 0
        search_params['ignore_logs'] = False
    if not search_params:
        logger.error('User %s tried to start a search but no data was provided', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, your old search history was deleted. Try to search again.',
                                       chat_id=chat_id)
        return ConversationHandler.END
    if search_params.get(QUERY):
        search_params[QUERY] = tss.google(search_params[QUERY], from_language='en', to_language='fi')
    if not starting_ind:
        logger.info('User {} is searching from item №{}:\n{}'.format(user.username or user.first_name, starting_ind,
                    beautiful_params))
        await context.bot.send_message(text='Searching for items with parameters:\n' + beautiful_params,
                                       chat_id=chat_id)
    else:
        logger.info('User {} is continuing searching from item №{}'.format(user.username or user.first_name,
                                                                           starting_ind))
    finished_on, items = list_announcements(**search_params, starting_ind=starting_ind)
    if not items:
        await context.bot.send_message(text='Sorry, no items were found with these filters.', chat_id=chat_id)
        return ConversationHandler.END
    if not context.user_data.get('items'):
        context.user_data['items'] = items
    else:
        context.user_data['items'] = context.user_data['items'] + items
    if len(context.user_data['items']) > MAX_SAVED_LISTINGS:
        context.user_data['items'] = context.user_data['items'][-MAX_SAVED_LISTINGS:]
    beautified = beautify_items(items)
    if not starting_ind:
        await context.bot.send_message(text='Here you go! I hope you will find what you are looking for.',
                                       chat_id=chat_id)
    for i in range(len(items)):
        keyboard = [[
            InlineKeyboardButton('Get more info', callback_data=items[i]['uid']),
            InlineKeyboardButton('Open in tori.fi', url=items[i]['link'])
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=items[i]['image'], caption=beautified[i],
                                         reply_markup=reply_markup, parse_mode='HTML')
        except error.BadRequest:
            logger.warning('Bad Image {}'.format(items[i]['image'] or 'None'))
            await context.bot.send_message(chat_id=chat_id, text=beautified[i], reply_markup=reply_markup,
                                           parse_mode='HTML')
    await context.bot.send_message(text='Press to show {} more'.format(MAX_ITEMS_PER_SEARCH), chat_id=chat_id,
                                   reply_markup=
                                   InlineKeyboardMarkup([[InlineKeyboardButton('Show more', callback_data=
                                                          str(finished_on) + '_show_more')]]))
    return END


@log_and_update()
async def more_info_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Parses the CallbackQuery and shows more info about selection.
    """
    query = update.callback_query
    user = update.callback_query.from_user

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    user_data = context.user_data
    logger.info('User %s is checking out the details of the listing', user.username or user.first_name)

    if not user_data:
        logger.warning('User %s tried to repeat last search but no data available', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, your old search history was deleted. Try to search again.',
                                       chat_id=update.effective_chat.id)
        return
    listing = [item for item in (user_data.get('items') or []) if item['uid'] == query.data]
    if not listing:
        logger.warning('User %s tried to get more info on object that expired', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, this object is no longer accessible. Try to search again.',
                                       chat_id=update.effective_chat.id)
        return
    listing = listing[0]
    logger.info('More info url: {}'.format(listing['link']))
    listing = listing_info(listing['link'])
    maps_url = 'https://www.google.com/maps/place/' + listing['location'][-1].replace(' ', '+')

    keyboard = [[
        InlineKeyboardButton('Open in tori.fi', url=listing['link']),
        InlineKeyboardButton('Google Maps', url=maps_url),
        InlineKeyboardButton('Hide', callback_data=DELETE_MESSAGE)
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # await query.edit_message_text(text=beautify_listing(listing))
    if listing['image']:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=listing['image'],
                                     caption=beautify_listing(listing), reply_markup=reply_markup, parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=beautify_listing(listing, trim=False),
                                       reply_markup=reply_markup, parse_mode='HTML')


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Remove job with given name. Returns whether job was removed.
    """
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def collect_data(context: ContextTypes.DEFAULT_TYPE):
    """
    Collects data and sends message if new item has appeared on tori
    """
    job = context.job
    user_data = job.data
    beautiful_params = user_data['beautiful_params']

    if not user_data:
        logger.error('User %s tried to start a search but no data was provided', user_data['user'])
        return ConversationHandler.END

    utc_time_now = datetime.now(timezone.utc)
    # one search per minute should be enough, so I've set max to 20-30 results per search
    prum, items = list_announcements(**user_data, max_items=TRACKING_INTERVAL / 60)
    user_data['ignore_logs'] = True
    items = list(filter(lambda x: x['date'] > (utc_time_now - timedelta(seconds=TRACKING_INTERVAL)), items))
    if not items:
        return
    text = 'New items have been found using the following parameters:\n{}'.format(beautiful_params)
    await context.bot.send_message(job.chat_id, text=text)
    if not user_data['original_data'].get('items'):
        user_data['original_data']['items'] = items
    else:
        user_data['original_data']['items'] = user_data['original_data']['items'] + items
    if len(user_data['original_data']['items']) > MAX_SAVED_LISTINGS:
        user_data['original_data']['items'] = user_data['original_data']['items'][-MAX_SAVED_LISTINGS:]
    beautified = beautify_items(items)

    for i in range(len(items)):
        keyboard = [[
            InlineKeyboardButton('Get more info', callback_data=items[i]['uid']),
            InlineKeyboardButton('Open in tori.fi', url=items[i]['link'])
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if items[i]['image']:
            await context.bot.send_photo(chat_id=job.chat_id, photo=items[i]['image'],
                                         caption=beautified[i], reply_markup=reply_markup, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=job.chat_id, text=beautified[i], reply_markup=reply_markup,
                                           parse_mode='HTML')


async def track_end(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends the message that informs about ended job.
    """
    job = context.job
    user_data = job.data
    await context.bot.send_message(job.chat_id, text='Tracking job with following parameters has ended:\n{}'
                                   .format(user_data['beautiful_params']))
    # if not context.job_queue.jobs():
    #     await set_extended_commands(context.bot)


@log_and_update()
async def start_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the info about the user and ends the conversation.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    search_params = copy.deepcopy(context.user_data.get(FEATURES, DEFAULT_SETTINGS))
    beautiful_params = params_beautifier(search_params)
    search_params['beautiful_params'] = beautiful_params
    search_params['user'] = user.username or user.first_name
    search_params['original_data'] = context.user_data
    search_params['ignore_logs'] = False
    chat_id = update.effective_chat.id

    if not search_params:
        logger.error('User %s tried to start a search but no data was provided', user.username or user.first_name)
        await update.message.reply_text('Sorry, your old search history was deleted. Try to search again.')
        return ConversationHandler.END

    if search_params.get(QUERY):
        search_params[QUERY] = tss.google(search_params[QUERY], from_language='en', to_language='fi')


    logger.info('User {} started tracking:\n{}'.format(user.username or user.first_name, beautiful_params))
    # job_removed = remove_job_if_exists(str(chat_id), context)  # Need to support multiple jobs
    text = 'Tracker has been set up. I hope you will find what you are looking for!\nMonitoring will be active <b>for' \
           ' 24 hours</b>.\n/unset_tracker - to stop the tracker at any point\n/unset_all - to cancel all ongoing' \
           ' trackers\n/list_trackers - to list all ongoing trackers\nActive filters:\n{}'.format(beautiful_params)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='HTML')
    job_name = generate_unique_job_name(context.job_queue.jobs())

    # await set_extended_commands(context.bot)

    search_params['created_at'] = datetime.now(timezone.utc)
    context.job_queue.run_repeating(collect_data, TRACKING_INTERVAL, chat_id=chat_id, last=MAX_TRACKING_TIME,
                                    name='tracker_' + job_name, data=search_params)
    context.job_queue.run_once(track_end, MAX_TRACKING_TIME, chat_id=chat_id,
                               name='timer_' + job_name, data=search_params)
    return ConversationHandler.END


@log_and_update()
async def unset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Remove the job if the user changed their mind. Shows list of jobs
    """
    jobs = [job for job in context.job_queue.jobs() if job.name.startswith('tracker_')]
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        return

    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    reply_options = [[InlineKeyboardButton('Created at: {}; {}'.format(
        job.data['created_at'].astimezone(pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b'),
        job.data['beautiful_params'].replace('\n', '; ')),
        callback_data=job.name)] for job in jobs]

    reply_markup = InlineKeyboardMarkup(reply_options)
    await update.message.reply_text('Select the trackers that you want to cancel.', reply_markup=reply_markup)


async def unset_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Unsets selected tracker
    """
    query = update.callback_query
    user = update.callback_query.from_user

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    job = context.job_queue.get_jobs_by_name(query.data)
    if not job:
        logger.warning('User %s. Error while finding job to remove', user.username or user.first_name)
        return
    job2 = context.job_queue.get_jobs_by_name('timer_' + query.data[query.data.index('_') + 1:])
    if not job2:
        logger.warning('User %s. Error while finding job timer to remove', user.username or user.first_name)
        return
    job[0].schedule_removal()
    job2[0].schedule_removal()
    logger.info('User %s removed a tracker', user.username or user.first_name)

    # if not context.job_queue.jobs():
    #     await set_extended_commands(context.bot)

    await context.bot.send_message(chat_id=update.effective_chat.id, text='Tracker has been removed.')


@log_and_update(log=True)
async def unset_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Remove all ongoing jobs
    """
    jobs = context.job_queue.jobs()
    # await set_extended_commands(context.bot)
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        return

    for job in jobs:
        job.schedule_removal()
    await update.message.reply_text('All trackers were removed.')


@log_and_update(log=True)
async def list_trackers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Lists ongoing trackers
    """
    jobs = [job for job in context.job_queue.jobs() if job.name.startswith('tracker_')]
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        logger.info('There are no ongoing trackers.')
        # await set_extended_commands(context.bot)
        return

    text = 'The following trackers are running:'
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    for job in jobs:
        text += '\n\u2022 Created at: {}\n{}'.format(job.data['created_at'].astimezone(
            pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b'), job.data['beautiful_params'])
    await update.message.reply_text(text)


def generate_unique_job_name(jobs):
    """
    Generates unique job name
    """
    job_name = str(uuid.uuid4())
    current_jobs = [job.name for job in jobs]
    while job_name in current_jobs:
        job_name = str(uuid.uuid4())
    return job_name


async def delete_message(update, context):
    """
    Deletes the message
    """
    await update.callback_query.message.delete()


async def uncaught_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Message in case random text is sent
    """
    msg = "Sorry, I didn't catch that. Try selecting one of the available options or use /help for more info."
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg)


def main() -> None:
    """
    Run the bot.
    """
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    filterwarnings(action='ignore', message=r".*CallbackQueryHandler", category=PTBUserWarning)
    location_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_location, pattern='^' + str(ADDING_LOCATION) + '$'
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(save_selection_list, pattern='^' + '$|^'.join(LOCATION_OPTIONS.keys()) + '$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(adding_location, pattern='^' + str(PAGE_1) + '$'),
            CallbackQueryHandler(adding_location_2, pattern='^' + str(PAGE_2) + '$'),
            CallbackQueryHandler(adding_location_3, pattern='^' + str(PAGE_3) + '$'),
            CallbackQueryHandler(adding_location_4, pattern='^' + str(PAGE_4) + '$'),
            CallbackQueryHandler(end_selecting, pattern='^' + str(END) + '$'),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            SHOWING: SHOWING,
        },
    )

    type_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_bid_type, pattern='^' + str(ADDING_TYPE) + '$'
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(save_selection_single, pattern='^' + '$|^'.join(BID_TYPES.keys()) + '$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(end_selecting, pattern='^' + str(END) + '$'),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            SHOWING: SHOWING,
        },
    )

    category_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_category, pattern='^' + str(ADDING_CATEGORY) + '$'
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(save_selection_single, pattern='^' + '$|^'.join(CATEGORIES.keys()) + '$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(end_selecting, pattern='^' + str(END) + '$'),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            SHOWING: SHOWING,
        },
    )

    query_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adding_query, pattern='^' + str(ADDING_QUERY) + '$')],
        states={
            TYPING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_input)],
            },
        fallbacks=[
            CallbackQueryHandler(clear_query, pattern='^' + str(CLEARING_QUERY) + '$'),
            CallbackQueryHandler(end_selecting, pattern='^' + str(END) + '$'),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            SHOWING: SHOWING,
        },
    )
    price_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_price, pattern='^' + str(ADDING_PRICE) + '$'
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(set_min_price, pattern='^' + str(MIN_PRICE) + '$'),
                CallbackQueryHandler(set_max_price, pattern='^' + str(MAX_PRICE) + '$'),
                CallbackQueryHandler(clear_price, pattern='^' + str(CLEARING_PRICE) + '$'),
            ],
            TYPING_STAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_input_stay)]
        },
        fallbacks=[
            CallbackQueryHandler(end_selecting, pattern='^' + str(END) + '$'),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            SHOWING: SHOWING,
        },
    )
    # Set up top level ConversationHandler (selecting action)
    # Because the states of the third level conversation map to the ones of the second level
    # conversation, we need to make sure the top level conversation can also handle them
    selection_handlers = [
        location_conv,
        type_conv,
        category_conv,
        query_conv,
        price_conv,
        CallbackQueryHandler(show_help, pattern='^' + str(HELP) + '$'),
        CallbackQueryHandler(clear_data, pattern='^' + str(CLEARING) + '$'),
        CallbackQueryHandler(start_searching, pattern='^' + str(END) + '$'),

    ]
    search_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search)],
        states={
            SHOWING: [CallbackQueryHandler(search, pattern='^' + str(END) + '$')],
            SELECTING_ACTION: selection_handlers,
            SELECTING_LEVEL: selection_handlers,
        },
        fallbacks=[CommandHandler('search', search)],
    )
    track_selection_handlers = [
        location_conv,
        type_conv,
        category_conv,
        query_conv,
        price_conv,
        CallbackQueryHandler(show_help, pattern='^' + str(HELP) + '$'),
        CallbackQueryHandler(clear_data, pattern='^' + str(CLEARING) + '$'),
        CallbackQueryHandler(start_tracking, pattern='^' + str(END) + '$'),
    ]
    track_handler = ConversationHandler(
        entry_points=[CommandHandler('set_tracker', search)],
        states={
            SHOWING: [CallbackQueryHandler(search, pattern='^' + str(END) + '$')],
            SELECTING_ACTION: track_selection_handlers,
            SELECTING_LEVEL: track_selection_handlers,
        },
        fallbacks=[CommandHandler('set_tracker', search)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_message))
    application.add_handler(search_handler)
    application.add_handler(track_handler)
    application.add_handler(CallbackQueryHandler(
        more_info_button, pattern='^[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CallbackQueryHandler(delete_message, pattern='^' + str(DELETE_MESSAGE) + '$'))
    application.add_handler(CallbackQueryHandler(start_searching, pattern='^[0-9]+_show_more$'))

    application.add_handler(CallbackQueryHandler(
        unset_tracker, pattern='^tracker_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CommandHandler('unset_tracker', unset))
    application.add_handler(CommandHandler('unset_all', unset_all))
    application.add_handler(CommandHandler('list_trackers', list_trackers))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, uncaught_message))
    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == '__main__':
    main()
