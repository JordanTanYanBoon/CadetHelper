import os
import asyncio
from datetime import datetime
import zoneinfo
from flask import Flask, request
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Initialize Flask App
app = Flask(__name__)

# Timezone Configuration (Singapore Time)
SGT = zoneinfo.ZoneInfo("Asia/Singapore")

# Conversation States
(
    REPORT_TYPE,
    # Ad Hoc States
    ADHOC_NAMES,
    ADHOC_FROM,
    ADHOC_TO,
    # Flight States
    FLIGHT_SELECT,
    FLIGHT_FROM,
    FLIGHT_TO,
    FLIGHT_TOTAL,
    FLIGHT_CURRENT,
    FLIGHT_STATUS,
    FLIGHT_OOC,
    FLIGHT_NOT_WITH_WING,
    FLIGHT_OTHERS,
) = range(13)

# Keyboards
MAIN_MENU = ReplyKeyboardMarkup([["📝 Movement Report"]], resize_keyboard=True)
TYPE_MENU = ReplyKeyboardMarkup(
    [["🚨 Ad Hoc", "✈️ Flight Movement"], ["❌ Cancel"]], resize_keyboard=True
)
FLIGHT_CHOICE_MENU = ReplyKeyboardMarkup(
    [["ALPHA", "BRAVO", "CHARLIE"], ["↩️️ Back", "❌ Cancel"]], resize_keyboard=True
)
STEP1_MENU = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
NAV_MENU = ReplyKeyboardMarkup([["↩️ Back", "❌ Cancel"]], resize_keyboard=True)


def parse_raw_names(text: str) -> list[str]:
    """Splits text lines and cleans them into uppercase strings."""
    return [line.strip().upper() for line in text.strip().split("\n") if line.strip()]


def format_numbered_list(names: list[str]) -> str:
    """Formats list of names into 1. NAME 2. NAME..."""
    return "\n".join(f"{i+1}. {name}" for i, name in enumerate(names))


def format_status_list(text: str) -> tuple[str, str]:
    """Formats status personnel or defaults to 00 if nil/none."""
    cleaned = text.strip()
    if cleaned.upper() in ["NIL", "NONE", "0", "NO", "-"]:
        return "00", ""

    lines = [line.strip().upper() for line in cleaned.split("\n") if line.strip()]
    count_str = f"{len(lines):02d}"
    formatted_items = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))
    return count_str, formatted_items


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ready! Tap below to start:", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select report type."""
    await update.message.reply_text(
        "Select the type of Movement Report:", reply_markup=TYPE_MENU
    )
    return REPORT_TYPE


# -------------------------------------------------------------------
# AD HOC MOVEMENT REPORT FLOW
# -------------------------------------------------------------------

async def start_adhoc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "1/3: Send the **NAMES** (one per line):",
        parse_mode="Markdown",
        reply_markup=STEP1_MENU,
    )
    return ADHOC_NAMES


async def get_adhoc_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_names = parse_raw_names(update.message.text)
    context.user_data["adhoc_raw_names"] = raw_names

    await update.message.reply_text(
        "2/3: Send **LOCATION A** (Starting location):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return ADHOC_FROM


async def back_to_adhoc_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_names = context.user_data.get("adhoc_raw_names", [])
    count = len(raw_names)
    raw_text = "\n".join(raw_names) if raw_names else "None"

    await update.message.reply_text(
        f"Going back to Step 1.\n\n*Total Count:* {count}\n\n```\n{raw_text}\n```\nSend updated **NAMES**:",
        parse_mode="Markdown",
        reply_markup=STEP1_MENU,
    )
    return ADHOC_NAMES


async def get_adhoc_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["adhoc_from"] = update.message.text.strip().upper()

    await update.message.reply_text(
        "3/3: Send **LOCATION B** (Destination):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return ADHOC_TO


async def back_to_adhoc_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("adhoc_from", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*Current Location A:* {current}\n\nSend **LOCATION A**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return ADHOC_FROM


async def get_adhoc_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    to_loc = update.message.text.strip().upper()
    raw_names = context.user_data.get("adhoc_raw_names", [])
    from_loc = context.user_data.get("adhoc_from", "")
    
    # Get Singapore Time
    current_time = datetime.now(SGT).strftime("%H%M")

    formatted_names = format_numbered_list(raw_names)

    report = (
        "AD HOC MOVEMENT REPORT\n\n"
        f"{formatted_names}\n\n"
        f"Movement from {from_loc} to {to_loc} @ {current_time}H"
    )

    await update.message.reply_text(f"```\n{report}\n```", parse_mode="Markdown")

    context.user_data.clear()
    await update.message.reply_text("Tap below for another:", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# -------------------------------------------------------------------
# FLIGHT MOVEMENT REPORT FLOW
# -------------------------------------------------------------------

async def start_flight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "1/8: Select Flight (ALPHA, BRAVO, or CHARLIE):", reply_markup=FLIGHT_CHOICE_MENU
    )
    return FLIGHT_SELECT


async def get_flight_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_name"] = update.message.text.strip().upper()
    await update.message.reply_text(
        "2/8: Send **LOCATION A** (Starting location):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_FROM


async def back_to_flight_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Going back to Step 1.\n\nSelect Flight (ALPHA, BRAVO, or CHARLIE):",
        reply_markup=FLIGHT_CHOICE_MENU,
    )
    return FLIGHT_SELECT


async def get_flight_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_from"] = update.message.text.strip().upper()
    await update.message.reply_text(
        "3/8: Send **LOCATION B** (Destination):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_TO


async def back_to_flight_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_from", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*Current Location A:* {current}\n\nSend **LOCATION A**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_FROM


async def get_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_to"] = update.message.text.strip().upper()
    await update.message.reply_text(
        "4/8: Send **TOTAL STRENGTH** (e.g., 37):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_TOTAL


async def back_to_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_to", "None")
    await update.message.reply_text(
        f"Going back to Step 3.\n\n*Current Location B:* {current}\n\nSend **LOCATION B**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_TO


async def get_flight_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_total"] = update.message.text.strip()
    await update.message.reply_text(
        "5/8: Send **CURRENT STRENGTH** (e.g., 37):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_CURRENT


async def back_to_flight_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_total", "None")
    await update.message.reply_text(
        f"Going back to Step 4.\n\n*Current Total Strength:* {current}\n\nSend **TOTAL STRENGTH**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_TOTAL


async def get_flight_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_current"] = update.message.text.strip()
    await update.message.reply_text(
        "6/8: Send **ON STATUS** personnel (Rank, Name & reason, one per line) or type 'NIL':",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_STATUS


async def back_to_flight_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_current", "None")
    await update.message.reply_text(
        f"Going back to Step 5.\n\n*Current Present Strength:* {current}\n\nSend **CURRENT STRENGTH**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_CURRENT


async def get_flight_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["status_raw"] = text
    context.user_data["status_count"] = count_str
    context.user_data["status_list"] = formatted_list

    await update.message.reply_text(
        "7/8: Send **OUT OF CAMP** personnel or type 'NIL':",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_OOC


async def back_to_flight_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_text = context.user_data.get("status_raw", "NIL")
    await update.message.reply_text(
        f"Going back to Step 6.\n\n*Current Status Input:*\n```\n{raw_text}\n```\nSend **ON STATUS** personnel:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_STATUS


async def get_flight_ooc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["ooc_raw"] = text
    context.user_data["ooc_count"] = count_str
    context.user_data["ooc_list"] = formatted_list

    await update.message.reply_text(
        "8/8: Send personnel **CURRENTLY NOT WITH WING** or type 'NIL':",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_NOT_WITH_WING


async def back_to_flight_ooc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_text = context.user_data.get("ooc_raw", "NIL")
    await update.message.reply_text(
        f"Going back to Step 7.\n\n*Current Out Of Camp Input:*\n```\n{raw_text}\n```\nSend **OUT OF CAMP** personnel:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_OOC


async def get_flight_not_with_wing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["nww_raw"] = text
    context.user_data["nww_count"] = count_str
    context.user_data["nww_list"] = formatted_list

    await update.message.reply_text(
        "Final Step: Send **OTHERS** remarks or type 'NIL':",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_OTHERS


async def back_to_flight_nww(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_text = context.user_data.get("nww_raw", "NIL")
    await update.message.reply_text(
        f"Going back to Step 8.\n\n*Current Not With Wing Input:*\n```\n{raw_text}\n```\nSend **CURRENTLY NOT WITH WING** personnel:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_NOT_WITH_WING


async def get_flight_others(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)

    # Get CAA timestamp in SGT
    now = datetime.now(SGT)
    caa_time = now.strftime("%H%MH %d%m%y")

    flight_name = context.user_data.get("flight_name", "")
    from_loc = context.user_data.get("flight_from", "")
    to_loc = context.user_data.get("flight_to", "")
    total_str = context.user_data.get("flight_total", "0")
    curr_str = context.user_data.get("flight_current", "0")

    status_count = context.user_data.get("status_count", "00")
    status_list = context.user_data.get("status_list", "")

    ooc_count = context.user_data.get("ooc_count", "00")
    ooc_list = context.user_data.get("ooc_list", "")

    nww_count = context.user_data.get("nww_count", "00")
    nww_list = context.user_data.get("nww_list", "")

    others_count = count_str
    others_list = formatted_list

    report_lines = [
        "MOVEMENT REPORT",
        "",
        f"{flight_name} FLIGHT",
        "",
        f"CAA: {caa_time}",
        "",
        f"Movement from {from_loc} to {to_loc}",
        "",
        f"TOTAL STRENGTH: {total_str}",
        f"CURRENT STRENGTH: {curr_str}",
        "",
        f"On Status: {status_count}",
    ]
    if status_list:
        report_lines.append(status_list)

    report_lines.extend(["", f"Out of Camp: {ooc_count}"])
    if ooc_list:
        report_lines.append(ooc_list)

    report_lines.extend(["", f"Currently Not With Wing: {nww_count}"])
    if nww_list:
        report_lines.append(nww_list)

    report_lines.extend(["", f"Others: {others_count}"])
    if others_list:
        report_lines.append(others_list)

    report_lines.extend(["", "Thank you Sirs, Ma'am and all"])

    full_report = "\n".join(report_lines)

    await update.message.reply_text(f"```\n{full_report}\n```", parse_mode="Markdown")

    context.user_data.clear()
    await update.message.reply_text("Tap below for another:", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# Initialize Telegram Application
TOKEN = os.getenv("BOT_TOKEN")
telegram_app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex("^📝 Movement Report$"), start_report),
    ],
    states={
        REPORT_TYPE: [
            MessageHandler(filters.Regex("^🚨 Ad Hoc$"), start_adhoc),
            MessageHandler(filters.Regex("^✈️ Flight Movement$"), start_flight),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        ],
        # Ad Hoc States
        ADHOC_NAMES: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_adhoc_names),
        ],
        ADHOC_FROM: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_adhoc_names),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_adhoc_from),
        ],
        ADHOC_TO: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_adhoc_from),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_adhoc_to),
        ],
        # Flight States
        FLIGHT_SELECT: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^(ALPHA|BRAVO|CHARLIE)$"), get_flight_select),
        ],
        FLIGHT_FROM: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_select),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_from),
        ],
        FLIGHT_TO: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_to),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_to),
        ],
        FLIGHT_TOTAL: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_to),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_total),
        ],
        FLIGHT_CURRENT: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_total),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_current),
        ],
        FLIGHT_STATUS: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_current),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_status),
        ],
        FLIGHT_OOC: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_status),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_ooc),
        ],
        FLIGHT_NOT_WITH_WING: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_ooc),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_not_with_wing),
        ],
        FLIGHT_OTHERS: [
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_nww),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_flight_others),
        ],
    },
    fallbacks=[
        MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        MessageHandler(filters.Regex("^📝 Movement Report$"), start_report),
    ],
)

telegram_app.add_handler(conv_handler)


# Webhook Endpoint for Vercel Serverless Function
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        async def process():
            async with telegram_app:
                update = Update.de_json(request.get_json(force=True), telegram_app.bot)
                await telegram_app.process_update(update)

        asyncio.run(process())
        return "OK", 200

    return "Bot is active!", 200