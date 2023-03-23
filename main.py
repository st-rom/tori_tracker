import copy
import inspect
import locale
import psycopg2
import pytz
import translators.server as tss
import uuid

from constants import *
from datetime import datetime, timedelta, timezone
from parsing import (beautify_items, list_announcements, listing_info, beautify_listing, params_beautifier, logger,
                     parse_psql_listings, get_saved_from_db)
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand,
                      ReplyKeyboardRemove)
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import (Application, CallbackQueryHandler, ContextTypes, ConversationHandler,
                          CommandHandler, MessageHandler, filters)
from telegram.warnings import PTBUserWarning
from warnings import filterwarnings


# DEFAULT_SETTINGS = {
#     LOCATION: ['Pirkanmaa', 'Tampere'],
#     TYPE_OF_LISTING: ['Any Type'],
#     MAX_PRICE: 100,
#     CATEGORY: 'Any Category',
#     QUERY: 'Laptop'
# }


def tori_wrapper(log=False, db_update=False):
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
            try:
                result = await func(*args, **kwargs)  # logging before execution, but saving after it
                if db_update and update:
                    conn = psycopg2.connect(database=DB_URL.path[1:],
                                            host=DB_URL.hostname,
                                            user=DB_URL.username,
                                            password=DB_URL.password,
                                            port=DB_URL.port)
                    cur = conn.cursor()
                    cur.execute(INSERT_USER_SQL.format(user.id, user.username or '', user.first_name or '',
                                                       user.last_name or ''))
                    conn.commit()
                    cur.close()
                    conn.close()
                return result
            except BadRequest as e:
                logger.error('Uncaught telegram exception BadRequest: {}'.format(str(e)))
            except NetworkError as e:
                logger.error('Uncaught telegram exception NetworkError: {}'.format(str(e)))
        return wrapper
    return decorator


async def post_init(application: Application) -> None:
    # set commands
    await application.bot.delete_my_commands()
    command = [BotCommand('search', 'to start a search or a tracker'),
               BotCommand('list_saved', 'to list all saved listings'),
               BotCommand('list_trackers', 'to list all active trackers'),
               BotCommand('help', 'to show a help message'),
               BotCommand('unset_tracker', 'to unset a specific tracker'),
               BotCommand('unset_all', 'to cancel all ongoing trackers'),
               ]
    await application.bot.set_my_commands(command)  # rules-bot


@tori_wrapper(log=True, db_update=True)
async def help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info('Might need help.')

    msg = '\ud83d\udd27 ' \
          'This bot allows you to search for available listings or track newly added items on tori.fi - the largest' \
          ' marketplace for second-hand goods in Finland.\n\n' \
          'To get started, use /search command. Choose the filters and search for the latest listings' \
          ' on Tori or create a tracker.\n\n' \
          'A tracker is a tool that allows you to automatically monitor new listings that meet your specific search' \
          " criteria. You'll receive a notification as soon as a matching listing is added to Tori. This means you" \
          " won't have to constantly check Tori for new items - the bot will do it for you!\n\n" \
          "Also, you can save your favorite findings. To see your saved listings use /list_saved command.\n\n" \
          'In case you confront an issue, please message me \ud83d\udc47\n\n' \
          '\U0001f468\u200D\U0001f527 Telegram: @stroman\n\u2709 Email: rom.stepaniuk@gmail.com'
    msg = msg.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg)


# Top level conversation callbacks
@tori_wrapper()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Starts the search conversation.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    if not context.user_data.get(FEATURES):
        context.user_data[QUERY_LANGUAGE] = QUERY_LANGUAGES[0]
        context.user_data[FEATURES] = copy.deepcopy(DEFAULT_SETTINGS)

    buttons = [
        [
            InlineKeyboardButton(text='Search Term \U0001F520', callback_data=str(ADD_QUERY)),
            InlineKeyboardButton(text='Location \ud83c\udf04', callback_data=str(ADD_LOCATION)),
        ],
        [
            InlineKeyboardButton(text='Listing Type \ud83c\udf81', callback_data=str(ADD_TYPE)),
            InlineKeyboardButton(text='Price Range \ud83d\udcb0', callback_data=str(ADD_PRICE)),
        ],
        [
            InlineKeyboardButton(text='Category \ud83c\udfbe', callback_data=str(ADD_CATEGORY)),
            InlineKeyboardButton(text='Clear Filters \u274c', callback_data=str(CLEAR)),
        ],
        [
            InlineKeyboardButton(text='Show Saved \u2764\ufe0f', callback_data=str(SHOW_SAVED)),
            InlineKeyboardButton(text='Help \u2753', callback_data=str(SHOW_HELP)),
        ],
        [
            InlineKeyboardButton(text='Start Tracking \U0001f440', callback_data=str(START_TRACKER)),
            InlineKeyboardButton(text='Search \ud83d\udd0e', callback_data=str(RUN_SEARCH)),
        ],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    text = 'Choose the filters you wish to apply.\n\n' \
           '\U0001F4CB Current Filters:\n{}\n\n' \
           'Press <b>Clear Filters \u274c</b> to remove all filters.\n' \
           'Press <b>Show Saved \u2764\ufe0f</b> to see all of your saved listings.\n' \
           'Press <b>Start Tracking \U0001f440</b> to create a tracker for newly added listings.\n' \
           'Press <b>Search \ud83d\udd0e</b> to search for available listings.'.format(
            params_beautifier(context.user_data[FEATURES]))
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await update.message.reply_text(text=text, reply_markup=keyboard, parse_mode='HTML')
    return SELECTING_ACTION


@tori_wrapper()
async def adding_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()
    btn = BACK_BTN
    if context.user_data.get(START_OVER):
        btn = CONFIRM_BTN

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_1.keys()), 2)),
        [InlineKeyboardButton(text='Next Page \u27a1', callback_data=LOC_PAGE_2)],
        [InlineKeyboardButton(text=btn, callback_data=TO_MENU)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    val_str = ', '.join(ud[FEATURES].get(context.user_data[CURRENT_FEATURE]))
    text = 'Current selections: {}.\n\n' \
           'Press <b>Next Page \u27a1</b> to see more options.\n' \
           'Press <b>{}</b> when done.\n\n' \
           'Choose out of the following locations:'.format(val_str, btn)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one.\n\n' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')

    return ADDING_LOCATION


@tori_wrapper()
async def adding_location_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()
    btn = BACK_BTN
    if context.user_data.get(START_OVER):
        btn = CONFIRM_BTN

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_2.keys()), 2)),
        [InlineKeyboardButton(text='Previous Page \u2b05', callback_data=LOC_PAGE_1),
         InlineKeyboardButton(text='Next Page \u27a1', callback_data=LOC_PAGE_3)],
        [InlineKeyboardButton(text=btn, callback_data=TO_MENU)],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    val_str = ', '.join(ud[FEATURES].get(context.user_data[CURRENT_FEATURE]))
    text = 'Current selections: {}.\n\n' \
           'Press <b>Next Page \u27a1</b> to see more options.\n' \
           'Press <b>{}</b> when done.\n\n' \
           'Choose out of the following locations:'.format(val_str, btn)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one.\n\n' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')

    return ADDING_LOCATION


@tori_wrapper()
async def adding_location_3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()
    btn = BACK_BTN
    if context.user_data.get(START_OVER):
        btn = CONFIRM_BTN

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_3.keys()), 2)),
        [InlineKeyboardButton(text='Previous Page \u2b05', callback_data=LOC_PAGE_2),
         InlineKeyboardButton(text='Next Page \u27a1', callback_data=LOC_PAGE_4)],
        [InlineKeyboardButton(text=btn, callback_data=TO_MENU)],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    val_str = ', '.join(ud[FEATURES].get(context.user_data[CURRENT_FEATURE]))
    text = 'Current selections: {}.\n\n' \
           'Press <b>Next Page \u27a1</b> to see more options.\n' \
           'Press <b>{}</b> when done.\n\n' \
           'Choose out of the following locations:'.format(val_str, btn)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one.\n\n' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')

    return ADDING_LOCATION


@tori_wrapper()
async def adding_location_4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    await update.callback_query.answer()
    btn = BACK_BTN
    if context.user_data.get(START_OVER):
        btn = CONFIRM_BTN

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(LOCATION_OPTIONS_4.keys()), 2)),
        [InlineKeyboardButton(text='Previous Page \u2b05', callback_data=LOC_PAGE_3)],
        [InlineKeyboardButton(text=btn, callback_data=TO_MENU)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    val_str = ', '.join(ud[FEATURES].get(context.user_data[CURRENT_FEATURE]))
    text = 'Current selections: {}.\n\n' \
           'Press <b>Previous Page \u2b05</b> to see previous options.\n' \
           'Press <b>{}</b> when done.\n\n' \
           'Choose out of the following locations:'.format(val_str, btn)
    if context.user_data.get(START_OVER):
        text = 'Location saved! If you want, you can add another one.\n\n' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')

    return ADDING_LOCATION


@tori_wrapper()
async def adding_bid_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected bid type
    """
    context.user_data[CURRENT_FEATURE] = TYPE_OF_LISTING
    ud = context.user_data
    await update.callback_query.answer()
    btn = BACK_BTN
    if context.user_data.get(START_OVER):
        btn = CONFIRM_BTN

    group = lambda flat, size: [[InlineKeyboardButton(text=k + (' \u2705' if ud[FEATURES].get(ud[CURRENT_FEATURE]) and
                                                                k in ud[FEATURES][ud[CURRENT_FEATURE]] else
                                                                ''), callback_data=k) for k in flat[i:i + size]]
                                for i in range(0, len(flat), size)]
    buttons = [
        *list(group(list(BID_TYPES.keys()), 2)),
        [InlineKeyboardButton(text=btn, callback_data=TO_MENU)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    optional_str = ''
    if 'Wanted to Buy' in ud[FEATURES][ud[CURRENT_FEATURE]] or 'Wanted to Rent' in ud[FEATURES][ud[CURRENT_FEATURE]]:
        optional_str = '\u2757 Keep in mind that <b>Wanted to Buy</b> and <b>Wanted to Rent</b> listings are ' \
                       'created by users who are POTENTIAL BUYERS.\n' \
                       'These filters should not be used if you are looking to buy/rent the items.\n' \
                       'If you are looking to buy or rent a property, please use the <b>For Sale</b> or' \
                       ' <b>For Rent</b> options instead.\n\n' \

    val_str = ', '.join(ud[FEATURES].get(context.user_data[CURRENT_FEATURE]))
    text = 'Choose a listing type:\n' \
           '• <b>For Sale</b>: items for sale\n' \
           '• <b>For Rent</b>: items for rent\n' \
           '• <b>Wanted to Buy</b>: users looking to buy specific items\n' \
           '• <b>Wanted to Rent</b>: users looking to rent specific items\n' \
           '• <b>Free</b>: items being given away for free\n' \
           '• <b>Any Type</b>: all listings\n\n{}' \
           'Current selections: {}.\n' \
           'Press <b>{}</b> when done.'.format(optional_str, val_str, btn)

    if context.user_data.get(START_OVER):
        text = 'Selection saved! If you want, you can add another one.\n\n' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')

    return ADDING_TYPE


@tori_wrapper()
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
        [InlineKeyboardButton(text=BACK_BTN, callback_data=TO_MENU)]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    text = 'Choose one of the following categories:'
    if ud[FEATURES].get(ud[CURRENT_FEATURE]):
        text = 'Current selection: {}.\n\n' \
               'To change it, select one of the following:'.format(ud[FEATURES][ud[CURRENT_FEATURE]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return ADDING_CATEGORY


@tori_wrapper()
async def adding_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for keywords feature.
    """
    context.user_data[CURRENT_FEATURE] = QUERY
    if context.user_data[QUERY_LANGUAGE] == 'Finnish':
        text = 'Enter the keywords <b>in Finnish</b> (e.g., kitara, sohva, luistimet).'
    elif context.user_data[QUERY_LANGUAGE] == 'Ukrainian':
        text = 'Напишіть ключові слова для пошуку <b>Українською</b> (напр. диван, мікрохвильовка, кіт і т.д.).'
    else:
        text = 'Enter the keywords <b>in English</b> (e.g., guitar, couch, ice skates, cat).'
    btn_text = 'Switch Language to {} \ud83d\udd24'.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    buttons = [[InlineKeyboardButton(text=btn_text.format(lang),
                                     callback_data=SWITCH_LANG + '_' + LANGUAGES_MAPPING[lang])] for
               lang in QUERY_LANGUAGES if lang != context.user_data[QUERY_LANGUAGE]]

    if context.user_data[FEATURES].get(QUERY):
        buttons.insert(0, [InlineKeyboardButton(text='Clear This Filter \u274c', callback_data=CLEAR_QUERY)])
        text += '\n\nCurrent search keywords: {}'.format(context.user_data[FEATURES].get(QUERY))

    buttons = InlineKeyboardMarkup(buttons + [[InlineKeyboardButton(text=BACK_BTN, callback_data=TO_MENU)]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons, parse_mode='HTML')

    return ADDING_QUERY


@tori_wrapper(log=True)
async def clear_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Clear query filters and return to feature selection.
    """
    context.user_data[FEATURES].pop(QUERY, None)
    context.user_data[QUERY_LANGUAGE] = QUERY_LANGUAGES[0]
    return await adding_query(update, context)


@tori_wrapper(log=True)
async def switch_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Switches to different language for query.
    """
    lang = update.callback_query.data[update.callback_query.data.find('_') + 1:]
    context.user_data[QUERY_LANGUAGE] = next(k for k, val in LANGUAGES_MAPPING.items() if val == lang)
    return await adding_query(update, context)


@tori_wrapper()
async def adding_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected price limitations
    """
    ud = context.user_data
    buttons = [[
        InlineKeyboardButton(text='Set up Min, €', callback_data=SET_MIN_PRICE),
        InlineKeyboardButton(text='Set up Max, €', callback_data=SET_MAX_PRICE),
    ],
        [InlineKeyboardButton(text=BACK_BTN, callback_data=TO_MENU)]
    ]
    text = 'Set up price filters \ud83d\udcb0'
    if ud[FEATURES].get(MIN_PRICE) or ud[FEATURES].get(MAX_PRICE):
        text = 'Current price filters:\n'
        buttons.insert(1, [InlineKeyboardButton(text='Clear Price Filters \u274c', callback_data=CLEAR_PRICE)])
        if ud[FEATURES].get(MIN_PRICE):
            text += '<b>Min price</b>: {}€\n'.format(ud[FEATURES].get(MIN_PRICE))
        if ud[FEATURES].get(MAX_PRICE):
            text += '<b>Max price</b>: {}€\n'.format(ud[FEATURES].get(MAX_PRICE))
        text += '\nYou can edit or clear your current price settings.'
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    keyboard = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='HTML')
    else:
        await update.message.reply_text(text=text, reply_markup=keyboard, parse_mode='HTML')
    return SELECTING_PRICE


@tori_wrapper(log=True)
async def set_min_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for min price.
    """
    context.user_data[CURRENT_FEATURE] = MIN_PRICE
    text = "Okay, tell me the min price, € (e.g., 10, 50, 100)"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BTN, callback_data=TO_MENU)]])

    await update.callback_query.answer()

    if context.user_data[FEATURES].get(TYPE_OF_LISTING) and 'Free' in context.user_data[FEATURES].get(TYPE_OF_LISTING):
        text = '\u2757 You have a filter for <b>Free</b> items selected \u2757\nIf you will proceed ' \
               'with <b>Min Price</b> filter it will reset your <b>Free</b> items selection.\n\n' + text
    text = text.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons, parse_mode='HTML')
    return ADDING_PRICE


@tori_wrapper(log=True)
async def set_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for max price.
    """
    context.user_data[CURRENT_FEATURE] = MAX_PRICE
    text = "Okay, tell me the max price, € (e.g., 10, 50, 100)"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BTN, callback_data=TO_MENU)]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons)
    return ADDING_PRICE


@tori_wrapper(log=True)
async def clear_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Clear price filters and return to feature selection.
    """
    context.user_data[FEATURES].pop(MIN_PRICE, None)
    context.user_data[FEATURES].pop(MAX_PRICE, None)

    return await adding_price(update, context)


@tori_wrapper()
async def end_selecting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    End gathering of features and return to parent conversation.
    """
    return await start(update, context)


@tori_wrapper()
async def save_selection_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Save multiple inputs for feature and return to feature selection.
    """
    user_data = context.user_data
    user_data[START_OVER] = True
    await update.callback_query.answer()
    if len(user_data[FEATURES].get(user_data[CURRENT_FEATURE])) == 1 and \
            user_data[FEATURES].get(user_data[CURRENT_FEATURE])[0].startswith('Any'):
        user_data[FEATURES].pop(user_data[CURRENT_FEATURE])

    if user_data[FEATURES].get(user_data[CURRENT_FEATURE]):
        if update.callback_query.data.startswith('Any'):
            user_data[FEATURES][user_data[CURRENT_FEATURE]] = [update.callback_query.data]
        elif update.callback_query.data not in user_data[FEATURES][user_data[CURRENT_FEATURE]]:
            user_data[FEATURES][user_data[CURRENT_FEATURE]].append(update.callback_query.data)
        else:
            user_data[FEATURES][user_data[CURRENT_FEATURE]].remove(update.callback_query.data)
    else:
        user_data[FEATURES][user_data[CURRENT_FEATURE]] = [update.callback_query.data]

    if not user_data[FEATURES][user_data[CURRENT_FEATURE]]:
        user_data[FEATURES][user_data[CURRENT_FEATURE]] = ANY_SETTINGS.get(user_data[CURRENT_FEATURE])

    if user_data[CURRENT_FEATURE] == TYPE_OF_LISTING and update.callback_query.data == 'Free':
        context.user_data[FEATURES].pop(MIN_PRICE, None)

    if update.callback_query.data in LOCATION_OPTIONS_1:
        return await adding_location(update, context)
    elif update.callback_query.data in LOCATION_OPTIONS_2:
        return await adding_location_2(update, context)
    elif update.callback_query.data in LOCATION_OPTIONS_3:
        return await adding_location_3(update, context)
    elif update.callback_query.data in LOCATION_OPTIONS_4:
        return await adding_location_4(update, context)
    elif update.callback_query.data in BID_TYPES:
        return await adding_bid_type(update, context)
    else:
        logger.error('Unpredicted behavior after saving selection {} in {}.'.format(update.callback_query.data,
                                                                                    user_data[CURRENT_FEATURE]))
        return await start(update, context)


@tori_wrapper()
async def save_selection_single(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Save input for feature and return to feature selection.
    """
    user_data = context.user_data
    await update.callback_query.answer()
    user_data[FEATURES][user_data[CURRENT_FEATURE]] = update.callback_query.data
    user_data[START_OVER] = True
    return await start(update, context)


@tori_wrapper()
async def save_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Save input for feature and return to feature selection.
    """
    user_data = context.user_data
    user_data[FEATURES][user_data[CURRENT_FEATURE]] = update.message.text
    user_data[START_OVER] = True
    return await start(update, context)


@tori_wrapper()
async def save_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Save input for feature and stay at feature modifier.
    """
    user_data = context.user_data
    try:
        val = int(update.message.text)
        if val >= 0:
            user_data[FEATURES][user_data[CURRENT_FEATURE]] = val
            if user_data[CURRENT_FEATURE] == MIN_PRICE and context.user_data[FEATURES].get(TYPE_OF_LISTING) and\
                    'Free' in context.user_data[FEATURES][TYPE_OF_LISTING]:
                context.user_data[FEATURES][TYPE_OF_LISTING].remove('Free')
        else:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "\u2757\u2757 Incorrect input format \u2757\u2757"
        )
    user_data[START_OVER] = True
    return await adding_price(update, context)


@tori_wrapper(log=True)
async def clear_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Clear all filters and return to feature selection.
    """
    context.user_data[FEATURES] = copy.deepcopy(ANY_SETTINGS)
    return await start(update, context)


@tori_wrapper(log=True)
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Shows help text
    """
    logger.info('Might need help.')
    await update.callback_query.edit_message_text(text=(
        "To search for the desired item, you can set up the following filters:\n\n"
        "• <b>Search Term \U0001F520</b> - add a search phrase in English, Finnish, or in Ukrainian to find exactly "
        "what you need (e.g., chair, kitara, fridge)\n"
        "• <b>Location \ud83c\udf04</b> - choose the city or the region where you want to find the item\n"
        "• <b>Listing Type \ud83c\udf81</b> - filter by items For Sale, For Rent, Free items and the Wanted"
        " posts specifically looking for particular goods to Rent or to Buy\n"
        "• <b>Price Range \ud83d\udcb0</b> - set up Min and Max ranges of prices\n"
        "• <b>Category \ud83c\udfbe</b> - choose a category of the items (e.g., Electronics, Hobbies, Vehicles)\n"
        "• <b>Clear Filters \u274c</b> - clear all of the filters (sets everything to any)\n"
        "• <b>Show Saved \u2764\ufe0f</b> - show all of the saved listings\n"
        "• <b>Help \u2753</b> - get a message with the descriptions of all buttons\n"
        "• <b>Start Tracking \U0001f440</b> - create a tracker that will notify you when a new listing that matches "
        "your filters is added to Tori\n"
        "• <b>Search \ud83d\udd0e</b> - search for available matching listings\n\n"
        "For other useful information use /help").encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE'),
                                                  reply_markup=InlineKeyboardMarkup(
                                                      [[InlineKeyboardButton(text=BACK_BTN, callback_data=TO_MENU)]]),
                                                  parse_mode='HTML'
                                                  )
    return ONLY_SHOWING


@tori_wrapper(db_update=True)
async def start_searching(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    End conversation and start the search.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    context.user_data['saved'] = get_saved_from_db(user.id, context.user_data.get('saved', []))
    search_params = copy.deepcopy(context.user_data.get(FEATURES, DEFAULT_SETTINGS))
    beautiful_params = params_beautifier(search_params)
    chat_id = update.effective_chat.id
    query = update.callback_query
    try:
        await query.answer('Loading...')
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
        return END
    if search_params.get(QUERY) and context.user_data[QUERY_LANGUAGE] != 'Finnish':
        search_params[QUERY] = tss.google(search_params[QUERY],
                                          from_language=LANGUAGES_MAPPING[context.user_data[QUERY_LANGUAGE]],
                                          to_language='fi')
    if not starting_ind:
        logger.info('User {} is searching from item №{}:\n{}'.format(user.username or user.first_name, starting_ind,
                                                                     beautiful_params))
        await update.callback_query.edit_message_text(text='Searching for items with parameters:\n' + beautiful_params,
                                                      disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        logger.info('User {} is continuing searching from item №{}'.format(user.username or user.first_name,
                                                                           starting_ind))
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    finished_on, items = list_announcements(**search_params, starting_ind=starting_ind)
    if not items:
        await context.bot.send_message(text='Sorry, no items were found with these filters.', chat_id=chat_id)
        return END
    if not context.user_data.get('items'):
        context.user_data['items'] = items
    else:
        context.user_data['items'] = context.user_data['items'] + items
    if len(context.user_data['items']) > MAX_SAVED_LISTINGS:
        context.user_data['items'] = context.user_data['items'][-MAX_SAVED_LISTINGS:]
    beautified = beautify_items(items, lang=LANGUAGES_MAPPING[context.user_data.get(QUERY_LANGUAGE, 'English')])

    saved_urls = [i['link'] for i in context.user_data.get('saved', [])]
    if not starting_ind:
        await context.bot.send_message(text='Here you go! I hope you will find what you are looking for.',
                                       chat_id=chat_id)
    for i in range(len(items)):
        saved_btn = InlineKeyboardButton('Remove from Saved \u274c', callback_data='keep-rm-item_' + items[i]['uid']) \
            if items[i]['link'] in saved_urls else \
            InlineKeyboardButton('Add to Saved \u2764\ufe0f', callback_data='add-item_' + items[i]['uid'])
        keyboard = [[
            InlineKeyboardButton('Show More Info', callback_data='keep-item_' + items[i]['uid']),
            InlineKeyboardButton('Open in tori.fi', url=items[i]['link'])],
            [saved_btn]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=items[i]['image'], caption=beautified[i],
                                         reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest:
            logger.warning('Bad Image {}'.format(items[i]['image'] or 'None'))
            await context.bot.send_message(chat_id=chat_id, text=beautified[i], reply_markup=reply_markup,
                                           parse_mode='HTML')
    await context.bot.send_message(text='Press to show {} more'.format(MAX_ITEMS_PER_SEARCH), chat_id=chat_id,
                                   reply_markup=InlineKeyboardMarkup(
                                       [[InlineKeyboardButton('Show More',
                                                              callback_data=str(finished_on) + '_show_more')]]))
    return END


@tori_wrapper(log=True, db_update=True)
async def more_info_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Parses the CallbackQuery and shows more info about selection.
    """
    query = update.callback_query
    user = update.callback_query.from_user
    chat_id = update.effective_chat.id

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    user_data = context.user_data
    if not user_data:
        logger.warning('User %s tried to repeat last search but no data available', user.username or user.first_name)
        await query.answer('\u2757 Not available \u2757\n'
                           'Sorry, something went wrong.\nTry to use /search again.', show_alert=True)
        return

    saved_items = user_data.get('saved') or []
    reg_items = user_data.get('items') or []
    unique_items = list(reg_items)
    unique_items.extend(x for x in saved_items if x not in unique_items)
    item_uid = query.data[query.data.find('_') + 1:] if query.data.startswith('keep') else query.data

    listing = [item for item in unique_items if item['uid'] == item_uid]
    if not listing:
        logger.warning('User %s tried to Show More Info on object that expired', user.username or user.first_name)
        await query.answer('\u2757 Not available \u2757\n'
                           'Sorry, this object is no longer accessible.\nTry to use /search again.', show_alert=True)
        await query.message.delete()
        return
    listing = listing[0]
    logger.info('More info url: {}'.format(listing['link']))
    listing_url = listing['link']
    listing = listing_info(listing_url)
    if type(listing) == str:
        if listing == listing_url:
            keyboard = InlineKeyboardMarkup([
                [query.message.reply_markup.inline_keyboard[0][1]],
                query.message.reply_markup.inline_keyboard[-1],
            ])
            await query.answer("Couldn't retrieve more info")
            await update.callback_query.edit_message_reply_markup(reply_markup=keyboard)
            return
        else:
            await query.answer('\u2757 Not available \u2757\nSorry, this object is no longer accessible.\n'
                               'Try to use /search again.', show_alert=True)
            await query.message.delete()
            return
    maps_url = 'https://www.google.com/maps/place/' + listing['location'][-1].replace(' ', '+')
    saved_urls = [i['link'] for i in context.user_data.get('saved', [])]
    if listing_url in saved_urls and not query.data.startswith('keep'):
        saved_btn = InlineKeyboardButton('Remove from Saved \u274c', callback_data='rm-item_' + item_uid)
    elif listing_url in saved_urls:
        saved_btn = InlineKeyboardButton('Remove from Saved \u274c', callback_data='keep-rm-item_' + item_uid)
    else:
        saved_btn = InlineKeyboardButton('Add to Saved \u2764\ufe0f', callback_data='add-item_' + item_uid)
    keyboard = [
        [
            InlineKeyboardButton('Google Maps', url=maps_url),
            InlineKeyboardButton('Open in tori.fi', url=listing_url)
        ],
        [
            saved_btn
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    lang = LANGUAGES_MAPPING[context.user_data.get(QUERY_LANGUAGE, 'English')]
    try:
        await query.edit_message_caption(beautify_listing(listing, lang=lang), parse_mode='HTML')
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest:
        await query.edit_message_text(text=beautify_listing(listing, trim=False, lang=lang), parse_mode='HTML',
                                      reply_markup=reply_markup)


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


@tori_wrapper()
async def collect_data(context: ContextTypes.DEFAULT_TYPE):
    """
    Collects data and sends message if new item has appeared on tori
    """
    job = context.job
    user_data = job.data
    beautiful_params = user_data['beautiful_params']

    if not user_data:
        logger.error('User %s tried to start a search but no data was provided', user_data['user'])
        return

    utc_time_now = datetime.now(timezone.utc)
    # one search per minute should be enough, so I've set max to 20-30 results per search
    prum, items = list_announcements(**user_data, max_items=TRACKING_INTERVAL / 60)
    user_data['ignore_logs'] = True
    items = list(filter(lambda x: x['date'] > (utc_time_now - timedelta(seconds=TRACKING_INTERVAL)), items))
    if not items:
        return
    if not user_data['original_data'].get('items'):
        user_data['original_data']['items'] = items
    else:
        user_data['original_data']['items'] = user_data['original_data']['items'] + items
    if len(user_data['original_data']['items']) > MAX_SAVED_LISTINGS:
        user_data['original_data']['items'] = user_data['original_data']['items'][-MAX_SAVED_LISTINGS:]
    beautified = beautify_items(items, lang=LANGUAGES_MAPPING[context.user_data.get(QUERY_LANGUAGE, 'English')])

    text = 'New items have been found using the following parameters:\n\n{}'.format(beautiful_params)
    await context.bot.send_message(job.chat_id, text=text)
    for i in range(len(items)):
        keyboard = [
            [
                InlineKeyboardButton('Show More Info', callback_data='keep-item_' + items[i]['uid']),
                InlineKeyboardButton('Open in tori.fi', url=items[i]['link'])
            ],
            [
                InlineKeyboardButton('Add to Saved \u2764\ufe0f', callback_data='add-item_' + items[i]['uid'])
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_photo(chat_id=job.chat_id, photo=items[i]['image'],
                                         caption=beautified[i], reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest:
            logger.warning('Bad Image in tracker {}'.format(items[i]['image'] or 'None'))
            await context.bot.send_message(chat_id=job.chat_id, text=beautified[i], reply_markup=reply_markup,
                                           parse_mode='HTML')


@tori_wrapper()
async def track_end(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Sends the message that informs about ended job.
    """
    job = context.job
    user_data = job.data
    await context.bot.send_message(job.chat_id, text='Tracking job with following parameters has ended:\n{}'
                                   .format(user_data['beautiful_params']))


@tori_wrapper(db_update=True)
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
        return END

    if search_params.get(QUERY) and context.user_data[QUERY_LANGUAGE] != 'Finnish':
        search_params[QUERY] = tss.google(search_params[QUERY],
                                          from_language=LANGUAGES_MAPPING[context.user_data[QUERY_LANGUAGE]],
                                          to_language='fi')

    logger.info('User {} started tracking:\n{}'.format(user.username or user.first_name, beautiful_params))
    # job_removed = remove_job_if_exists(str(chat_id), context)  # Need to support multiple jobs
    text = 'Tracker has been set up. I hope you will find what you are looking for!\n\n' \
           'Monitoring will be active <b>for 48 hours</b>.\n' \
           '/unset_tracker - to stop the tracker at any point\n' \
           '/unset_all - to cancel all ongoing trackers\n' \
           '/list_trackers - to list all ongoing trackers\n\n' \
           'Active filters:\n{}'.format(beautiful_params)

    await update.callback_query.edit_message_text(text=text, parse_mode='HTML')
    job_name = generate_unique_job_name(context.job_queue.jobs())

    search_params['created_at'] = datetime.now(timezone.utc)
    context.job_queue.run_repeating(collect_data, TRACKING_INTERVAL, chat_id=chat_id, last=MAX_TRACKING_TIME,
                                    name='tracker_' + job_name, data=search_params)
    context.job_queue.run_once(track_end, MAX_TRACKING_TIME, chat_id=chat_id,
                               name='timer_' + job_name, data=search_params)
    return END


@tori_wrapper(db_update=True)
async def unset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Remove the job if the user changed their mind. Shows list of jobs
    """
    jobs = [job for job in context.job_queue.jobs() if job.name.startswith('tracker_')]
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        return

    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    reply_options = [[InlineKeyboardButton('\U0001F7E2 Created at: {}; {}'.format(
        job.data['created_at'].astimezone(pytz.timezone('Europe/Helsinki')).strftime('%H:%M, %d %b'),
        job.data['beautiful_params'].replace('\n', '; ')),
        callback_data=job.name)] for job in jobs] + [[InlineKeyboardButton('Close \u274c',
                                                                           callback_data=DELETE_MESSAGE)]]

    reply_markup = InlineKeyboardMarkup(reply_options)
    await update.message.reply_text('Select the trackers that you want to cancel.', reply_markup=reply_markup)


@tori_wrapper(log=True, db_update=True)
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

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text='Tracker has been removed.')


@tori_wrapper(db_update=True)
async def unset_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ask to confirm all jobs unsetting
    """
    jobs = context.job_queue.jobs()
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(text='No \u274c', callback_data=DELETE_MESSAGE),
        InlineKeyboardButton(text='Yes, cancel all \u2705', callback_data=UNSET_ALL),
    ]])
    text = 'Are you sure you want to cancel all ongoing trackers?'
    await update.message.reply_text(text, reply_markup=keyboard)


@tori_wrapper(log=True)
async def unset_all_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Remove all ongoing jobs
    """
    for job in context.job_queue.jobs():
        job.schedule_removal()
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text='All trackers were removed.')


@tori_wrapper(log=True, db_update=True)
async def list_trackers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Lists ongoing trackers
    """
    jobs = [job for job in context.job_queue.jobs() if job.name.startswith('tracker_')]
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        logger.info('There are no ongoing trackers.')
        return

    text = 'The following trackers are running:'
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
    for job in jobs:
        text += '\n\n\u2022 Created at: {}\n{}'.format(job.data['created_at'].astimezone(
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


@tori_wrapper()
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deletes the message
    """
    await update.callback_query.message.delete()


@tori_wrapper()
async def delete_message_timed(context: ContextTypes.DEFAULT_TYPE):
    """
    Deletes the message after time
    """
    job = context.job
    await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)


@tori_wrapper()
async def uncaught_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Message in case random text is sent
    """
    msg = "Sorry, I didn't catch that.\nTry selecting one of the available options or use /help for more info."
    message = await context.bot.send_message(chat_id=update.message.chat_id, text=msg)
    context.job_queue.run_once(delete_message_timed, MSG_DESTRUCTION_TIMEOUT, chat_id=message.chat_id,
                               name='timeout_' + str(message.message_id), data=message.message_id)


@tori_wrapper(log=True)
async def add_to_saved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Adds listing to Saved
    """
    query = update.callback_query
    user = update.callback_query.from_user

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    user_data = context.user_data
    if not user_data:
        logger.error('User %s tried to add to saved but no data available', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, your old search history was deleted. Try to search again.',
                                       chat_id=update.effective_chat.id)
        return

    saved_items = user_data.get('saved') or []
    reg_items = user_data.get('items') or []
    unique_items = list(reg_items)
    unique_items.extend(x for x in saved_items if x not in unique_items)
    listing = [item for item in unique_items if item['uid'] == query.data[query.data.find('_') + 1:]]
    if not listing:
        logger.warning('User %s tried to save on object that expired', user.username or user.first_name)
        await query.answer('\u2757 Not available \u2757\n'
                           'Sorry, this object is no longer accessible.\nTry to use /search again.', show_alert=True)
        await query.message.delete()
        return
    listing = listing[0]
    keyboard = InlineKeyboardMarkup([
        query.message.reply_markup.inline_keyboard[0],
        [InlineKeyboardButton('Remove from Saved \u274c', callback_data='keep-rm-item_' + listing['uid'])]
    ])
    await update.callback_query.edit_message_reply_markup(reply_markup=keyboard)
    conn = psycopg2.connect(database=DB_URL.path[1:],
                            host=DB_URL.hostname,
                            user=DB_URL.username,
                            password=DB_URL.password,
                            port=DB_URL.port)
    cur = conn.cursor()
    cur.execute(INSERT_LISTING_SQL.format(listing['uid'], user.id, listing['link'], listing['title'], listing['price'],
                                          listing['image'], listing['date'], listing['bid_type'], user.id))
    data = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    items = parse_psql_listings(data)
    context.user_data['saved'] = items
    logger.info('Added to Saved listing url: {}'.format(listing['link']))


@tori_wrapper(log=True, db_update=True)
async def list_saved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    List listings from Saved
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    chat_id = update.effective_chat.id
    if update.callback_query:
        await update.callback_query.answer()

    items = get_saved_from_db(user.id, context.user_data.get('saved', []))
    context.user_data['saved'] = items
    if not items:
        await context.bot.send_message(chat_id=chat_id, text='Your list of saved listings is empty.')
        return END
    beautified = beautify_items(items, lang=LANGUAGES_MAPPING[context.user_data.get(QUERY_LANGUAGE, 'English')])
    text = '\u2764\ufe0f Here are your saved listings! \u2764\ufe0f'.encode(
           'utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    await context.bot.send_message(text=text, chat_id=chat_id)
    for i in range(len(items)):
        keyboard = [[
            InlineKeyboardButton('Show More Info', callback_data=items[i]['uid']),
            InlineKeyboardButton('Open in tori.fi', url=items[i]['link'])],
            [InlineKeyboardButton('Remove from Saved \u274c', callback_data='rm-item_' + items[i]['uid'])]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=items[i]['image'], caption=beautified[i],
                                         reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest:
            logger.warning('Bad Image {}'.format(items[i]['image'] or 'None'))
            await context.bot.send_message(chat_id=chat_id, text=beautified[i], reply_markup=reply_markup,
                                           parse_mode='HTML')
    return END


@tori_wrapper(log=True)
async def remove_from_saved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Removes a selected listing from Saved
    """
    query = update.callback_query
    user = query.from_user

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    user_data = context.user_data
    if not user_data:
        logger.error('User %s tried to add to saved but no data available', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, your old search history was deleted. Try to search again.',
                                       chat_id=update.effective_chat.id)
        return

    saved_items = user_data.get('saved') or []
    reg_items = user_data.get('items') or []
    unique_items = list(reg_items)
    unique_items.extend(x for x in saved_items if x not in unique_items)
    listing = [item for item in unique_items if item['uid'] == query.data[query.data.find('_') + 1:]]
    if not listing:
        logger.warning('User %s tried to save on object that expired', user.username or user.first_name)
        await query.answer('\u2757 Not available \u2757\n'
                           'Sorry, this object is no longer accessible.\nTry to use /search again.', show_alert=True)
        await query.message.delete()
        return
    listing = listing[0]
    conn = psycopg2.connect(database=DB_URL.path[1:],
                            host=DB_URL.hostname,
                            user=DB_URL.username,
                            password=DB_URL.password,
                            port=DB_URL.port)
    cur = conn.cursor()
    cur.execute(DELETE_LISTING_SQL.format(user.id, listing['link'], user.id))
    data = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    items = parse_psql_listings(data)
    context.user_data['saved'] = items
    logger.info('Removed listing url: {}'.format(listing['link']))
    if query.data.startswith('keep'):
        keyboard = InlineKeyboardMarkup([
            query.message.reply_markup.inline_keyboard[0],
            [InlineKeyboardButton('Add to Saved \u2764\ufe0f', callback_data='add-item_' + listing['uid'])]
        ])
        await query.edit_message_reply_markup(reply_markup=keyboard)
    else:
        await query.message.delete()


def main() -> None:
    """
    Run the bot.
    """
    # Create the Application and pass it your bot token.
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    filterwarnings(action='ignore', message=r".*CallbackQueryHandler", category=PTBUserWarning)

    # Set up top level ConversationHandler (selecting action)
    search_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('search', start),
        ],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(adding_query, pattern='^' + str(ADD_QUERY) + '$'),
                CallbackQueryHandler(adding_location, pattern='^' + str(ADD_LOCATION) + '$'),
                CallbackQueryHandler(adding_bid_type, pattern='^' + str(ADD_TYPE) + '$'),
                CallbackQueryHandler(adding_price, pattern='^' + str(ADD_PRICE) + '$'),
                CallbackQueryHandler(adding_category, pattern='^' + str(ADD_CATEGORY) + '$'),
                CallbackQueryHandler(show_help, pattern='^' + str(SHOW_HELP) + '$'),
                CallbackQueryHandler(clear_filters, pattern='^' + str(CLEAR) + '$'),
                CallbackQueryHandler(list_saved, pattern='^' + str(SHOW_SAVED) + '$'),
            ],
            ONLY_SHOWING: [],
            ADDING_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_input),
                CallbackQueryHandler(clear_query, pattern='^' + str(CLEAR_QUERY) + '$'),
                CallbackQueryHandler(switch_language, pattern='^' + str(SWITCH_LANG) + '_[a-z]{2}$'),
            ],
            ADDING_LOCATION: [
                CallbackQueryHandler(save_selection_list, pattern='^' + '$|^'.join(LOCATION_OPTIONS.keys()) + '$'),
                CallbackQueryHandler(adding_location, pattern='^' + str(LOC_PAGE_1) + '$'),
                CallbackQueryHandler(adding_location_2, pattern='^' + str(LOC_PAGE_2) + '$'),
                CallbackQueryHandler(adding_location_3, pattern='^' + str(LOC_PAGE_3) + '$'),
                CallbackQueryHandler(adding_location_4, pattern='^' + str(LOC_PAGE_4) + '$'),
            ],
            ADDING_TYPE: [
                CallbackQueryHandler(save_selection_list, pattern='^' + '$|^'.join(BID_TYPES.keys()) + '$'),
            ],
            SELECTING_PRICE: [
                CallbackQueryHandler(set_min_price, pattern='^' + str(SET_MIN_PRICE) + '$'),
                CallbackQueryHandler(set_max_price, pattern='^' + str(SET_MAX_PRICE) + '$'),
                CallbackQueryHandler(clear_price, pattern='^' + str(CLEAR_PRICE) + '$'),
            ],
            ADDING_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_price),
            ],
            ADDING_CATEGORY: [
                CallbackQueryHandler(save_selection_single, pattern='^' + '$|^'.join(CATEGORIES.keys()) + '$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(start_searching, pattern='^' + str(RUN_SEARCH) + '$'),
            CallbackQueryHandler(start_tracking, pattern='^' + str(START_TRACKER) + '$'),
            CallbackQueryHandler(end_selecting, pattern='^' + str(TO_MENU) + '$'),
        ],
        allow_reentry=True
    )

    application.add_handler(search_handler)
    application.add_handler(CommandHandler('help', help_message))

    application.add_handler(CallbackQueryHandler(start_searching, pattern='^[0-9]+_show_more$'))
    application.add_handler(CallbackQueryHandler(delete_message, pattern='^' + str(DELETE_MESSAGE) + '$'))
    application.add_handler(CallbackQueryHandler(unset_all_confirmed, pattern='^' + str(UNSET_ALL) + '$'))

    application.add_handler(CommandHandler('list_saved', list_saved))
    application.add_handler(CommandHandler('list_trackers', list_trackers))
    application.add_handler(CommandHandler('unset_tracker', unset))
    application.add_handler(CommandHandler('unset_all', unset_all))

    application.add_handler(CallbackQueryHandler(
        more_info_button, pattern='^[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CallbackQueryHandler(
        unset_tracker, pattern='^tracker_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CallbackQueryHandler(
        add_to_saved, pattern='^add-item_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CallbackQueryHandler(
        remove_from_saved, pattern='^rm-item_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CallbackQueryHandler(
        remove_from_saved, pattern='^keep-rm-item_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CallbackQueryHandler(
        more_info_button, pattern='^keep-item_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, uncaught_message))
    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == '__main__':
    main()
