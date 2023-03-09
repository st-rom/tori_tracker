import copy
import inspect
import locale
import logging
import pytz
import translators.server as tss
import uuid

from constants import *
from datetime import datetime, timedelta, timezone
from parsing import beautify_items, list_announcements, listing_info, beautify_listing, params_beautifier
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand, error,
                      ReplyKeyboardRemove)
from telegram.ext import (Application, CallbackQueryHandler, ContextTypes, ConversationHandler,
                          CommandHandler, MessageHandler, filters)
from telegram.warnings import PTBUserWarning
from warnings import filterwarnings


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
QUERY = 'search_query'
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


async def post_init(application: Application) -> None:
    bot = application.bot
    # set commands
    command = [BotCommand('start', 'to start the bot'),
               BotCommand('search', 'to search for new available items'),
               BotCommand('set_tracker', 'to set up a tracker for a particular search'),
               BotCommand('cancel', 'to cancel ongoing operation'),
               BotCommand('list_trackers', 'to list all active trackers'),
               BotCommand('unset_tracker', 'to unset a particular tracker'),
               BotCommand('unset_all', 'to cancel all ongoing trackers'),
               ]
    await bot.set_my_commands(command)  # rules-bot


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info('Bot activated by user {} with id {}'.format(user.username or user.first_name, user.id))

    msg = 'Hey! Welcome to Tori Tracker!\nHere you can quickly get the list of latest available items on tori.fi and' \
          ' set up the tracker for particular items that you are interested in.\nTo get started select one of' \
          ' the following commands:\n\t•/search - to search for new available items\n\t•/set_tracker - to set up a' \
          ' tracker for a particular search'
    reply_markup = ReplyKeyboardRemove()
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg, reply_markup=reply_markup)
    # # Languages message
    # msg = 'Hey! Welcome to Tori Tracker!\nHere you can quickly get the list of latest available items on tori.fi and' \
    #       'set up the tracker for particular listings that you are interested in.\nPlease, choose a language:'
    #
    # # Languages menu
    # languages_keyboard = [
    #     [KeyboardButton('Suomi')],
    #     [KeyboardButton('English')],
    #     [KeyboardButton('Українська')]
    # ]
    # reply_kb_markup = ReplyKeyboardMarkup(languages_keyboard, resize_keyboard=True, one_time_keyboard=True)
    # await context.bot.send_message(chat_id=update.message.chat_id, text=msg, reply_markup=reply_kb_markup)


# Top level conversation callbacks
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Starts the search conversation and asks the user about their location.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    text = 'Choose the filters you wish to apply for the search.\nTo abort, simply type /cancel.' \
           '\nWhen ready, press `Search \ud83d\udd0e` button.'.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    if not context.user_data.get(FEATURES):
        context.user_data[FEATURES] = copy.deepcopy(DEFAULT_SETTINGS)

    buttons = [
        [
            InlineKeyboardButton(text='Search terms \ud83d\udd24', callback_data=str(ADDING_QUERY)),
            InlineKeyboardButton(text='Location \ud83c\udf04', callback_data=str(ADDING_LOCATION)),
        ],
        [
            InlineKeyboardButton(text='Listing type \ud83c\udf81', callback_data=str(ADDING_TYPE)),
            InlineKeyboardButton(text='Price \ud83d\udcb0', callback_data=str(ADDING_PRICE)),
        ],
        [
            InlineKeyboardButton(text='Category \ud83c\udfbe', callback_data=str(ADDING_CATEGORY)),
            InlineKeyboardButton(text='Help \u2753', callback_data=str(HELP)),
        ],
        [
            InlineKeyboardButton(text='Clear filters \u274c', callback_data=str(CLEARING)),
            InlineKeyboardButton(text='Show filters \ud83d\udc40', callback_data=str(SHOWING)),
        ],
        [
            InlineKeyboardButton(text='Search \ud83d\udd0e', callback_data=str(END)),
        ],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # If we're starting over we don't need to send a new message
    if context.user_data[FEATURES] != DEFAULT_SETTINGS:
        text += '\n\u2757 Search parameters are set up \u2757\n' \
                'Press `Clear filters \u274c` to reset them.\nPress' \
                ' `Show filters \ud83d\udc40` to see them.\n'.encode('utf-16_BE', 'surrogatepass').decode('utf-16_BE')
    if context.user_data.get(START_OVER) and update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    elif context.user_data.get(START_OVER):
        logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
        await update.message.reply_text(
            "Selection saved successfully! Let's see what's available on tori right now!"
        )
        await update.message.reply_text(text=text, reply_markup=keyboard)
    else:
        if update.message.text == '/set_tracker':
            intro = 'Set up a tracker for the items you are looking for. As soon as new one will appear you will get' \
                   ' a notification.'
        else:
            intro = 'Set up filters for the desired search and find the items you need.'
        await update.message.reply_text(intro)
        await update.message.reply_text(text=text, reply_markup=keyboard)

    context.user_data[START_OVER] = False
    return SELECTING_ACTION


async def adding_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected location
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    context.user_data[CURRENT_FEATURE] = LOCATION
    ud = context.user_data
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
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
    text = 'Choose out of the following locations:'
    if context.user_data.get(START_OVER):
        text = "Location saved! If you want you can add another one. " + text
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
    text = 'Choose out of the following locations:'
    if context.user_data.get(START_OVER):
        text = "Location saved! If you want you can add another one. " + text
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
    text = 'Choose out of the following locations:'
    if context.user_data.get(START_OVER):
        text = "Location saved! If you want you can add another one. " + text
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
    text = 'Choose out of the following locations:'
    if context.user_data.get(START_OVER):
        text = "Location saved! If you want you can add another one. " + text
    context.user_data[START_OVER] = False

    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


async def adding_bid_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected bid type
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    context.user_data[CURRENT_FEATURE] = TYPE_OF_LISTING
    ud = context.user_data
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
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
               "To change it select one of the following:".format(ud[FEATURES][ud[CURRENT_FEATURE]])
    context.user_data[START_OVER] = False

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


async def adding_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected category
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    context.user_data[CURRENT_FEATURE] = CATEGORY
    ud = context.user_data
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
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
               "To change it select one of the following:".format(ud[FEATURES][ud[CURRENT_FEATURE]])
    context.user_data[START_OVER] = False

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)

    return SELECTING_FILTER


async def adding_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for keywords feature.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    context.user_data[CURRENT_FEATURE] = QUERY
    text = 'Enter the keywords(e.g. guitar, couch, ice skates)'
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


async def clear_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Clear query filters and return to feature selection.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    context.user_data[FEATURES].pop(QUERY, None)
    context.user_data[START_OVER] = True

    return await adding_query(update, context)


async def adding_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the selected price limitations
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    ud = context.user_data
    # context.user_data[FEATURES][]
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
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
        text += 'You can edit or clear your current price settings'

    keyboard = InlineKeyboardMarkup(buttons)
    call_func = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    if update.callback_query:
        await update.callback_query.answer()
    if ud[FEATURES].get(TYPE_OF_LISTING) == 'Free':
        await call_func(text='Price settings do not work with `Free` listing type filter',
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]]))
    else:
        await call_func(text=text, reply_markup=keyboard)
    return SELECTING_FILTER


async def set_min_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for min price.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    context.user_data[CURRENT_FEATURE] = MIN_PRICE
    text = "Okay, tell me min price, €"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons)
    return TYPING_STAY


async def set_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Prompt user to input data for max price.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    context.user_data[CURRENT_FEATURE] = MAX_PRICE
    text = "Okay, tell me max price, €"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]])

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=text, reply_markup=buttons)
    return TYPING_STAY


async def clear_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Clear price filters and return to feature selection.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
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
        if update.callback_query.data not in user_data[FEATURES][user_data[CURRENT_FEATURE]]:
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


async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Clear all filters and return to feature selection.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    context.user_data[FEATURES] = copy.deepcopy(DEFAULT_SETTINGS)
    context.user_data[START_OVER] = True

    return await search(update, context)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Shows help text
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    await update.callback_query.edit_message_text(text=(
        "To search for the desired item you can set up the following search filters:\n"
        "• Search terms \ud83d\udd24 - add a search phrase in English to find exactly what you need (e.g. chair,"
        " fridge, guitar)\n"
        "• Location \ud83c\udf04 - choose the city or the region, where you want to find the item\n"
        "• Listing type \ud83c\udf81 - you can filter by Free items, Renting or Regular items\n"
        "• Price \ud83d\udcb0 - set up Min and Max ranges of prices\n"
        "• Category \ud83c\udfbe - choose a category of the items (e.g. cars, hobby, furniture)\n"
        "• Help \u2753 - get a message with the description of all buttons\n"
        "• Clear filters \u274c - clears all of the previously selected filters (resets to defaults)\n"
        "• Show filters \ud83d\udc40 - shows you ALL filters that you've previously set up\n"
        "• Search \ud83d\udd0e - press this button to start the search").encode('utf-16_BE',
                                                                                'surrogatepass').decode('utf-16_BE'),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK, callback_data=END)]])
    )
    context.user_data[START_OVER] = True

    return SHOWING


async def show_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Pretty print gathered data.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))

    search_params = context.user_data.get(FEATURES, {})
    buttons = [[InlineKeyboardButton(text=BACK, callback_data=str(END))]]
    keyboard = InlineKeyboardMarkup(buttons)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text=params_beautifier(search_params), reply_markup=keyboard)
    context.user_data[START_OVER] = True
    return SHOWING


async def cancel_nested(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Completely end conversation from within nested conversation.
    """
    user = update.message.from_user
    logger.info("User %s canceled nested conversation.", user.username or user.first_name)

    return STOPPING


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """End Conversation by command."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.username or user.first_name)
    await update.message.reply_text('Operation cancelled')

    return END


async def start_searching(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    End conversation and start the search.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    logger.info('Function {} executed by {}'.format(inspect.stack()[0][3], user.username or user.first_name))
    search_params = copy.deepcopy(context.user_data.get(FEATURES, DEFAULT_SETTINGS))
    beautiful_params = params_beautifier(search_params)
    chat_id = update.effective_chat.id
    query = update.callback_query
    try:
        await query.answer()
        if query.data.endswith('show_more'):
            await update.callback_query.edit_message_text(text='Showing more listing:')
            starting_ind = int(query.data.split('_')[0])
        else:
            starting_ind = 0
    except AttributeError as e:
        starting_ind = 0
    if not search_params:
        logger.info('User %s tried to start a search but no data was available', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, your last search history was deleted due to a new update.'
                                            '\nPlease try to use /search instead.', chat_id=chat_id)
        return ConversationHandler.END
    if search_params.get(QUERY):
        search_params[QUERY] = tss.google(search_params[QUERY], from_language='en', to_language='fi')
    logger.info('User {} is searching from item №{}:\n{}'.format(user.username or user.first_name, starting_ind,
                beautiful_params))
    query_phrase = ' (query: {})'.format(search_params.get(QUERY)) if search_params.get(QUERY) else ''
    loc_str = ', '.join(search_params.get(LOCATION)) if type(search_params.get(LOCATION)) == list else\
        search_params.get(LOCATION)
    if not starting_ind:
        await context.bot.send_message(text='Searching fo items with parameter:\n' + beautiful_params
                                       .format(search_params.get(TYPE_OF_LISTING), query_phrase, loc_str),
                                       chat_id=chat_id)
    finished_on, items = list_announcements(**search_params, starting_ind=starting_ind)
    if not items:
        await context.bot.send_message(text='Sorry, no items were found with these filters', chat_id=chat_id)
        return ConversationHandler.END
    context.user_data['items'] = items
    beautified = beautify_items(items)
    if not starting_ind:
        await context.bot.send_message(text='Here you go! I hope you will find what you are looking for!',
                                       chat_id=chat_id)
    for i in range(len(items)):
        keyboard = [[
            InlineKeyboardButton('Get more info', callback_data=i),
            InlineKeyboardButton('Open in tori.fi', url=items[i]['link'])
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=items[i]['image'], caption=beautified[i],
                                         reply_markup=reply_markup, parse_mode='HTML')
        except error.BadRequest:
            logger.info('Bad Image {}'.format(items[i]['image'] or 'None'))
            await context.bot.send_message(chat_id=chat_id, text=beautified[i], reply_markup=reply_markup,
                                           parse_mode='HTML')
    await context.bot.send_message(text='Press to show {} more'.format(MAX_ITEMS_PER_SEARCH), chat_id=chat_id,
                                   reply_markup=
                                   InlineKeyboardMarkup([[InlineKeyboardButton('Show more', callback_data=
                                                          str(finished_on) + '_show_more')]]))
    return END


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
        logger.info('User %s tried to repeat last search but no data available', user.username or user.first_name)
        await context.bot.send_message(text='Sorry, your last search history was deleted due to a new update.'
                                            '\nPlease try to use /search instead.', chat_id=update.effective_chat.id)
        return

    logger.info('More info url: {}'.format(user_data['items'][int(query.data)]['link']))
    listing = listing_info(user_data['items'][int(query.data)]['link'])
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
        logger.info('User %s tried to start a search but no data was available',
                    user_data['username'] or user_data['first_name'])
        await context.bot.send_message(job.chat_id, text='Sorry, your last search history was deleted due to a'
                                                         ' new update.\nPlease try to use /search again.')
        return ConversationHandler.END

    utc_time_now = datetime.now(timezone.utc)
    prum, items = list_announcements(**user_data, max_items=TRACKING_INTERVAL / 60)
    items = list(filter(lambda x: x['date'] > (utc_time_now - timedelta(seconds=TRACKING_INTERVAL)), items))
    if not items:
        logger.info('No new items found')
        return
    text = 'New items have been found using the following parameters:\n{}'.format(beautiful_params)
    await context.bot.send_message(job.chat_id, text=text)
    user_data['items'] = items
    beautified = beautify_items(items)

    for i in range(len(items)):
        keyboard = [[
            InlineKeyboardButton('Get more info', callback_data=i),
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


async def start_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the info about the user and ends the conversation.
    """
    user = update.message.from_user if update.message else update.callback_query.from_user
    search_params = copy.deepcopy(context.user_data.get(FEATURES, DEFAULT_SETTINGS))
    beautiful_params = params_beautifier(search_params)
    search_params['beautiful_params'] = beautiful_params
    search_params['username'] = user.username
    search_params['first_name'] = user.first_name
    chat_id = update.effective_chat.id

    if not search_params:
        logger.info('User %s tried to start a search but no data was available', user.username or user.first_name)
        await update.message.reply_text('Sorry, your last search history was deleted due to a new update.'
                                        '\nPlease try to use /search instead.')
        return ConversationHandler.END

    if search_params.get(QUERY):
        search_params[QUERY] = tss.google(search_params[QUERY], from_language='en', to_language='fi')


    logger.info('User {} started tracking:\n{}'.format(user.username or user.first_name, beautiful_params))
    # job_removed = remove_job_if_exists(str(chat_id), context)  # Need to support multiple jobs
    text = 'Tacker has been set up! The tracker will be active for 24 hours. I hope you will find what you are' \
           ' looking for!\n/unset_tracker - to stop the tracker at any point\n/unset_all - to cancel all ongoing' \
           ' trackers\n/list_trackers - to list all ongoing trackers\nActive filters:\n{}'.format(beautiful_params)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    job_name = generate_unique_job_name(context.job_queue.jobs())

    search_params['created_at'] = datetime.now(timezone.utc)
    context.job_queue.run_repeating(collect_data, TRACKING_INTERVAL, chat_id=chat_id, last=MAX_TRACKING_TIME,
                                    name='tracker_' + job_name, data=search_params)
    context.job_queue.run_once(track_end, MAX_TRACKING_TIME, chat_id=chat_id,
                               name='timer_' + job_name, data=search_params)
    return ConversationHandler.END


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
        logger.info('User %s. Error while finding job to remove', user.username or user.first_name)
        return
    job2 = context.job_queue.get_jobs_by_name('timer_' + query.data[query.data.index('_') + 1:])
    if not job2:
        logger.info('User %s. Error while finding job timer to remove', user.username or user.first_name)
        return
    job[0].schedule_removal()
    job2[0].schedule_removal()
    logger.info('User %s removed a tracker', user.username or user.first_name)

    await context.bot.send_message(chat_id=update.effective_chat.id, text='Tracker has been removed')


async def unset_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Remove all ongoing jobs
    """
    jobs = context.job_queue.jobs()
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
        return

    for job in jobs:
        job.schedule_removal()
    await update.message.reply_text('All trackers were removed.')


async def list_trackers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Lists ongoing trackers
    """
    jobs = [job for job in context.job_queue.jobs() if job.name.startswith('tracker_')]
    if not jobs:
        await update.message.reply_text('There are no ongoing trackers.')
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


def main() -> None:
    """
    Run the bot.
    """
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)
    location_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_location, pattern="^" + str(ADDING_LOCATION) + "$"
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(save_selection_list, pattern='^' + '$|^'.join(LOCATION_OPTIONS.keys()) + '$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(adding_location, pattern="^" + str(PAGE_1) + "$"),
            CallbackQueryHandler(adding_location_2, pattern="^" + str(PAGE_2) + "$"),
            CallbackQueryHandler(adding_location_3, pattern="^" + str(PAGE_3) + "$"),
            CallbackQueryHandler(adding_location_4, pattern="^" + str(PAGE_4) + "$"),
            CallbackQueryHandler(end_selecting, pattern="^" + str(END) + "$"),
            CommandHandler('cancel', cancel_nested),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            STOPPING: STOPPING,
            SHOWING: SHOWING,
        },
    )

    type_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_bid_type, pattern="^" + str(ADDING_TYPE) + "$"
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(save_selection_single, pattern='^' + '$|^'.join(BID_TYPES.keys()) + '$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(end_selecting, pattern="^" + str(END) + "$"),
            CommandHandler('cancel', cancel_nested),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            STOPPING: STOPPING,
            SHOWING: SHOWING,
        },
    )

    category_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_category, pattern="^" + str(ADDING_CATEGORY) + "$"
            )
        ],
        states={
            SELECTING_FILTER: [
                CallbackQueryHandler(save_selection_single, pattern='^' + '$|^'.join(CATEGORIES.keys()) + '$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(end_selecting, pattern="^" + str(END) + "$"),
            CommandHandler('cancel', cancel_nested),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            STOPPING: STOPPING,
            SHOWING: SHOWING,
        },
    )

    query_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adding_query, pattern="^" + str(ADDING_QUERY) + "$")],
        states={
            TYPING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_input)],
            },
        fallbacks=[
            CallbackQueryHandler(clear_query, pattern='^' + str(CLEARING_QUERY) + '$'),
            CallbackQueryHandler(end_selecting, pattern="^" + str(END) + "$"),
            CommandHandler('cancel', cancel_nested),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            STOPPING: STOPPING,
            SHOWING: SHOWING,
        },
    )
    price_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                adding_price, pattern="^" + str(ADDING_PRICE) + "$"
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
            CallbackQueryHandler(end_selecting, pattern="^" + str(END) + "$"),
            CommandHandler('cancel', cancel_nested),
        ],
        map_to_parent={
            # Return to second level menu
            END: SELECTING_LEVEL,
            # End conversation altogether
            STOPPING: STOPPING,
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
        CallbackQueryHandler(show_help, pattern="^" + str(HELP) + "$"),
        CallbackQueryHandler(clear_data, pattern="^" + str(CLEARING) + "$"),
        CallbackQueryHandler(show_data, pattern="^" + str(SHOWING) + "$"),
        CallbackQueryHandler(start_searching, pattern="^" + str(END) + "$"),

    ]
    search_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search)],
        states={
            SHOWING: [CallbackQueryHandler(search, pattern="^" + str(END) + "$")],
            SELECTING_ACTION: selection_handlers,
            SELECTING_LEVEL: selection_handlers,
            STOPPING: [CommandHandler('search', search)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(cancel, pattern="^" + str(STOPPING) + "$"),
                   ],
    )
    track_selection_handlers = [
        location_conv,
        type_conv,
        category_conv,
        query_conv,
        price_conv,
        CallbackQueryHandler(show_help, pattern="^" + str(HELP) + "$"),
        CallbackQueryHandler(clear_data, pattern="^" + str(CLEARING) + "$"),
        CallbackQueryHandler(show_data, pattern="^" + str(SHOWING) + "$"),
        CallbackQueryHandler(start_tracking, pattern="^" + str(END) + "$"),
    ]
    track_handler = ConversationHandler(
        entry_points=[CommandHandler('set_tracker', search)],
        states={

            SHOWING: [CallbackQueryHandler(search, pattern="^" + str(END) + "$")],
            SELECTING_ACTION: track_selection_handlers,
            SELECTING_LEVEL: track_selection_handlers,
            STOPPING: [CommandHandler('search', search)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(cancel, pattern="^" + str(STOPPING) + "$"),
                   ],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(search_handler)
    application.add_handler(track_handler)
    application.add_handler(CallbackQueryHandler(more_info_button, pattern='^[0-9]+$'))
    application.add_handler(CallbackQueryHandler(delete_message, pattern="^" + str(DELETE_MESSAGE) + "$"))
    application.add_handler(CallbackQueryHandler(start_searching, pattern='^[0-9]+_show_more$'))

    application.add_handler(CallbackQueryHandler(
        unset_tracker, pattern='^tracker_[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}$'))
    application.add_handler(CommandHandler('unset_tracker', unset))
    application.add_handler(CommandHandler('unset_all', unset_all))
    application.add_handler(CommandHandler('list_trackers', list_trackers))
    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == '__main__':
    main()
