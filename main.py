import asyncio
import locale
import logging
import os
import pytz
import re
import requests
import telegram as tg
import time
import translators as ts
import translators.server as tss

from bs4 import BeautifulSoup, NavigableString
from datetime import datetime, timedelta
from dotenv import load_dotenv
# from components.util import build_command_list
from telegram.ext import (ApplicationBuilder, Application, CallbackQueryHandler, ContextTypes, ConversationHandler,
                          CommandHandler, MessageHandler, filters)
from constants import *
from parsing import beautify_items, list_announcements, listing_info, beautify_listing


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
LOCATION, BID_TYPE, SEARCH_QUERY = range(3)


async def post_init(application: Application) -> None:
    bot = application.bot
    # set commands
    command = [tg.BotCommand('start', 'to start the bot'), tg.BotCommand('search', 'to search for new available items'),
               tg.BotCommand('repeat', 'to repeat the last search')]
    await bot.set_my_commands(command)  # rules-bot


async def start(update: tg.Update, context: ContextTypes.DEFAULT_TYPE):
    print(context)
    user = update.message.from_user
    logger.info('Bot activated by user {} with id {}'.format(user.username or user.first_name, user.id))

    # Languages message
    msg = 'Hey! Welcome to Tori Tracker!\nHere you can quickly get the list of latest available items on tori.fi and' \
          'set up the tracker for particular listings that you are interested in.\nPlease, choose a language:'

    # Languages menu
    languages_keyboard = [
        [tg.KeyboardButton('Suomi')],
        [tg.KeyboardButton('English')],
        [tg.KeyboardButton('Українська')]
    ]
    reply_kb_markup = tg.ReplyKeyboardMarkup(languages_keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=update.message.chat_id, text=msg, reply_markup=reply_kb_markup)


async def search(update: tg.Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the conversation and asks the user about their location."""
    reply_keyboard = [list(LOCATION_OPTIONS.keys())]
    print(reply_keyboard)

    await update.message.reply_text(
        "Hi! Let's see what's available on tori right now!\n"
        "Send /cancel at any point if you want to stop this search.\n"
        "Which location do you wish to search in?",
        reply_markup=tg.ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Choose the region"
        ),
    )
    return LOCATION


async def location(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the selected location and asks for a listing type."""
    user = update.message.from_user
    logger.info("Location of %s: %s", user.username or user.first_name, update.message.text)
    reply_keyboard = [list(BID_TYPES.keys())]

    await update.message.reply_text(
        "I see! Now choose what kind of listing types you are looking for.",
        reply_markup=tg.ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder='Choose a type'
        ),
    )

    user_data = context.user_data
    user_data['location'] = update.message.text
    return BID_TYPE


async def listing_type(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the selected listing type and asks for a search query."""
    user = update.message.from_user
    logger.info("Listings type of %s: %s", user.username or user.first_name, update.message.text)

    await update.message.reply_text("Enter the _*search keyword*_ \(in *English*\) if you are looking for something particular or send /skip if you don't need it\.", parse_mode='MarkdownV2')

    user_data = context.user_data
    user_data['bid_type'] = update.message.text
    return SEARCH_QUERY


async def query_search(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the info about the user and ends the conversation."""
    user = update.message.from_user
    user_data = context.user_data
    user_data['search_query'] = tss.google(update.message.text, from_language='fi', to_language='en')\
        if update.message.text and update.message.text != '/cancel' else ''

    logger.info("Search query of %s: %s", user.username or user.first_name, update.message.text)
    await update.message.reply_text('Searching for {} items in {} region...'.format(user_data['bid_type'],
                                                                                    user_data['location']))
    items = list_announcements(**user_data)
    if not items:
        await update.message.reply_text('Sorry, no items were found with these filters')
        return ConversationHandler.END
    user_data['items'] = items
    beautified = beautify_items(items)

    await update.message.reply_text('Here you go! I hope you will find what you are looking for!')
    for i in range(len(items)):
        keyboard = [[
            tg.InlineKeyboardButton('Get more info', callback_data=i),
            tg.InlineKeyboardButton('Link', url=items[i]['link'])
        ]]
        reply_markup = tg.InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(beautified[i], reply_markup=reply_markup, parse_mode='HTML')

    return ConversationHandler.END


async def repeat(update: tg.Update, context: ContextTypes.DEFAULT_TYPE):
    """Repeats last action"""
    user = update.message.from_user
    user_data = context.user_data

    logger.info('Listings type of %s: %s', user.username or user.first_name, update.message.text)
    await update.message.reply_text('Searching for {} items in {} region...'.format(user_data['bid_type'],
                                                                                    user_data['location']))
    items = list_announcements(**user_data)
    if not items:
        await update.message.reply_text('Sorry, no items were found with these filters')
        return
    user_data['items'] = items
    beautified = beautify_items(items)

    await update.message.reply_text('Here you go! I hope you will find what you are looking for!')
    for i in range(len(items)):
        keyboard = [[
            tg.InlineKeyboardButton('Get more info', callback_data=i),
            tg.InlineKeyboardButton('Link', url=items[i]['link'])
        ]]
        reply_markup = tg.InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(beautified[i], reply_markup=reply_markup, parse_mode='HTML')


async def cancel(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.id)
    await update.message.reply_text(
        "Bye! I hope we can do this again some day.", reply_markup=tg.ReplyKeyboardRemove()
    )

    return ConversationHandler.END


async def more_info_button(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    user_data = context.user_data
    print(9999999999999999999999999, query.data, type(query.data))
    listing = listing_info(user_data['items'][int(query.data)]['link'])
    maps_url = 'https://www.google.com/maps/place/' + listing['address'][-1].replace(' ', '+')

    keyboard = [[
        tg.InlineKeyboardButton('Link', url=listing['link']),
        tg.InlineKeyboardButton('Google Maps', url=maps_url)
    ]]
    reply_markup = tg.InlineKeyboardMarkup(keyboard)
    # await query.edit_message_text(text=beautify_listing(listing))
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=listing['image'],
                                 caption=beautify_listing(listing), reply_markup=reply_markup, parse_mode='HTML')

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    start_handler = CommandHandler('start', start)
    search_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search)],
        states={
            LOCATION: [MessageHandler(filters.Regex('^(Tampere|Pirkanmaa|Any)$'), location)],
            BID_TYPE: [MessageHandler(filters.Regex('^(Free|Not free|Any)$'), listing_type)],
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_search)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    repeat_handler = CommandHandler('repeat', repeat)

    application.add_handler(start_handler)
    application.add_handler(search_handler)
    application.add_handler(repeat_handler)
    application.add_handler(CallbackQueryHandler(more_info_button))

    application.run_polling()
