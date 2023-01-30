import asyncio
import json
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
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
# from components.util import build_command_list
from telegram.ext import (ApplicationBuilder, Application, CallbackQueryHandler, ContextTypes, ConversationHandler,
                          CommandHandler, MessageHandler, filters, Updater)
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
               tg.BotCommand('repeat', 'to repeat the last search'),
               tg.BotCommand('set_tracker', 'to set up a tracker for a particular search'),
               tg.BotCommand('unset_tracker', 'to cancel ongoing trackers')]
    await bot.set_my_commands(command)  # rules-bot


async def start(update: tg.Update, context: ContextTypes.DEFAULT_TYPE):
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
    """Starts the search conversation and asks the user about their location."""
    user = update.message.from_user
    logger.info("User %s started the search", user.username or user.first_name)
    reply_keyboard = [list(LOCATION_OPTIONS.keys())]

    if update.message.text != '/set_tracker':
        text = "Let's set up a tracker for the items you desire.\nSend /cancel at any point if you want to stop this" \
               " set up.\nWhich location do you wish to search in?"
    else:
        text = "Hi! Let's see what's available on tori right now!\nSend /cancel at any point if you want to stop this" \
               " search.\nWhich location do you wish to search in?"
    await update.message.reply_text(text,
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
    logger.info("Chosen listings type of %s: %s", user.username or user.first_name, update.message.text)

    await update.message.reply_text("Enter the _*search keyword*_ in *English* \(e\.g\. bed, microwave, Hervanta\) if"
                                    " you are looking for something particular\.\nSend /skip to skip this step\.",
                                    parse_mode='MarkdownV2')

    user_data = context.user_data
    user_data['bid_type'] = update.message.text
    return SEARCH_QUERY


async def query_search(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the info about the user and ends the conversation."""
    user = update.message.from_user
    user_data = context.user_data

    if not user_data:
        logger.info('User %s tried to start a search but no data was available', user.username or user.first_name)
        await update.message.reply_text('Sorry, your last search history was deleted due to a new update.'
                                        '\nPlease try to use /search instead.')
        return ConversationHandler.END

    if update.message.text != '/repeat':
        user_data['search_query'] = tss.google(update.message.text, from_language='en', to_language='fi')\
            if update.message.text and update.message.text != '/skip' else ''

    logger.info('User %s is searching: %s, %s, %s', user.username or user.first_name,
                user_data.get('location'), user_data.get('bid_type'), user_data.get('query'))
    query_phrase = ' (query: {})'.format(user_data.get('query')) if user_data.get('query') else ''
    await update.message.reply_text('Searching for {} items{} in {} region...'.format(user_data['bid_type'],
                                                                                      query_phrase,
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


async def cancel(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.username or user.first_name)
    await update.message.reply_text(
        "Bye! I hope we can do this again some day.", reply_markup=tg.ReplyKeyboardRemove()
    )

    return ConversationHandler.END


async def more_info_button(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    user = update.callback_query.from_user

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    user_data = context.user_data
    logger.info('User %s is checking out the details of the listing', user.username or user.first_name)

    if not user_data:
        logger.info('User %s tried to repeat last search but no data available', user.username or user.first_name)
        await update.message.reply_text('Sorry, your last search history was deleted due to a new update.'
                                        '\nPlease try to use /search instead.')
        return

    # print(9999999999999999999999999, query.data, type(query.data))
    listing = listing_info(user_data['items'][int(query.data)]['link'])
    maps_url = 'https://www.google.com/maps/place/' + listing['location'][-1].replace(' ', '+')
    logger.info('Listing url: {}'.format(listing['link']))
    # logger.info('Listing title: {}', listing['title'][0])
    # logger.info('Listing title: {}', str(listing['title'][0]))

    keyboard = [[
        tg.InlineKeyboardButton('Link', url=listing['link']),
        tg.InlineKeyboardButton('Google Maps', url=maps_url)
    ]]
    reply_markup = tg.InlineKeyboardMarkup(keyboard)
    # await query.edit_message_text(text=beautify_listing(listing))
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=listing['image'],
                                 caption=beautify_listing(listing), reply_markup=reply_markup, parse_mode='HTML')


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def collect_data(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_data = job.data

    if not user_data:
        logger.info('User %s tried to start a search but no data was available',
                    user_data['username'] or user_data['first_name'])
        await context.bot.send_message(job.chat_id, text='Sorry, your last search history was deleted due to a'
                                                         ' new update.\nPlease try to use /search again.')
        return ConversationHandler.END

    logger.info('User %s is tracking: %s, %s, %s', user_data['username'] or user_data['first_name'],
                user_data.get('location'), user_data.get('bid_type'), user_data.get('query'))
    utc_time_now = datetime.now(timezone.utc)
    items = list_announcements(**user_data, max_items=50)
    items = list(filter(lambda x: x['date'] > (utc_time_now - timedelta(seconds=TRACKING_INTERVAL)), items))
    if not items:
        logger.info('No new items found')
        return
    query_phrase = ' (query: {})'.format(user_data.get('query')) if user_data.get('query') else ''
    text = 'New {} items{} in {} region have been found:'.format(user_data['bid_type'], query_phrase,
                                                                 user_data['location'])
    await context.bot.send_message(job.chat_id, text=text)
    user_data['items'] = items
    beautified = beautify_items(items)

    for i in range(len(items)):
        keyboard = [[
            tg.InlineKeyboardButton('Get more info', callback_data=i),
            tg.InlineKeyboardButton('Link', url=items[i]['link'])
        ]]
        reply_markup = tg.InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(job.chat_id, text=beautified[i], reply_markup=reply_markup, parse_mode='HTML')


async def track_query_search(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the info about the user and ends the conversation."""
    user = update.message.from_user
    user_data = context.user_data
    user_data['username'] = user.username
    user_data['first_name'] = user.first_name

    if not user_data:
        logger.info('User %s tried to start a search but no data was available', user.username or user.first_name)
        await update.message.reply_text('Sorry, your last search history was deleted due to a new update.'
                                        '\nPlease try to use /search instead.')
        return ConversationHandler.END

    if update.message.text != '/repeat':
        user_data['search_query'] = tss.google(update.message.text, from_language='en', to_language='fi')\
            if update.message.text and update.message.text != '/skip' else ''

    logger.info('User %s is searching: %s, %s, %s', user.username or user.first_name,
                user_data.get('location'), user_data.get('bid_type'), user_data.get('query'))
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)  # Need to support multiple jobs
    query_phrase = ' (query: {})'.format(user_data.get('query')) if user_data.get('query') else ''
    text = 'Tacker for {} items{} in {} region has been set up!'.format(user_data['bid_type'], query_phrase,
                                                                        user_data['location'])
    if job_removed:
        text += " Old one was removed."
    await update.message.reply_text(text + ' The tracker will be active for 12 hours. I hope you will find what you'
                                           ' are looking for!\nSend /unset_tracker at any point if you want to stop'
                                           ' the tracker.\n')
    context.job_queue.run_repeating(collect_data, TRACKING_INTERVAL, chat_id=chat_id, name=str(chat_id), data=user_data,
                                    last=MAX_TRACKING_TIME)
    return ConversationHandler.END


async def unset(update: tg.Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the job if the user changed their mind."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = "Timer successfully cancelled!" if job_removed else "You have no active timer."
    await update.message.reply_text(text)



if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    start_handler = CommandHandler('start', start)
    search_handler = ConversationHandler(
        entry_points=[CommandHandler('search', search)],
        states={
            LOCATION: [MessageHandler(filters.Regex('^(Tampere|Pirkanmaa|Any)$'), location)],
            BID_TYPE: [MessageHandler(filters.Regex('^(Free|Not free|Any)$'), listing_type)],
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_search),
                           CommandHandler('skip', query_search)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    track_handler = ConversationHandler(
        entry_points=[CommandHandler('set_tracker', search)],
        states={
            LOCATION: [MessageHandler(filters.Regex('^(Tampere|Pirkanmaa|Any)$'), location)],
            BID_TYPE: [MessageHandler(filters.Regex('^(Free|Not free|Any)$'), listing_type)],
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_query_search),
                           CommandHandler('skip', track_query_search)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    repeat_handler = CommandHandler('repeat', query_search)

    application.add_handler(start_handler)
    application.add_handler(search_handler)
    application.add_handler(track_handler)
    application.add_handler(repeat_handler)
    application.add_handler(CallbackQueryHandler(more_info_button))
    # application.add_handler(CommandHandler("set", set_timer))
    application.add_handler(CommandHandler('unset_tracker', unset))

    application.run_polling()
