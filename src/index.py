import os
import asyncio
from datetime import datetime
import zoneinfo
from flask import Flask, request
from telegram import (
    ReplyKeyboardMarkup,
    Update,
)
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
    FLIGHT_CATEGORY_MENU,
    FLIGHT_ENTER_STATUS,
    FLIGHT_ENTER_OOC,
    FLIGHT_ENTER_NWW,
    FLIGHT_ENTER_OTHERS,
) = range(14)

# Reply Keyboards
MAIN_MENU = ReplyKeyboardMarkup([["📝 Movement Report"]], resize_keyboard=True)

TYPE_MENU = ReplyKeyboardMarkup(
    [
        ["🚨 Ad Hoc", "🚨 Ad Hoc (Arrival)"],
        ["✈️ Flight Movement", "✈️ Flight (Arrival)"],
        ["❌ Cancel"]
    ], 
    resize_keyboard=True
)

FLIGHT_CHOICE_MENU = ReplyKeyboardMarkup(
    [["ALPHA", "BRAVO", "CHARLIE"], ["↩️ Back", "❌ Cancel"]], resize_keyboard=True
)

STEP1_MENU = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
NAV_MENU = ReplyKeyboardMarkup([["↩️ Back", "❌ Cancel"]], resize_keyboard=True)

# New Keyboard for Quick Locations
LOC_NAV_MENU = ReplyKeyboardMarkup(
    [
        ["SAFTI GUARDROOM", "AIR WINGLINE", "SAFTI MI"],
        ["DHA", "SAFTI PARADE SQUARE"],
        ["↩️ Back", "❌ Cancel"]
    ], 
    resize_keyboard=True
)

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

def get_category_keyboard(user_data: dict) -> ReplyKeyboardMarkup:
    """Generates reply buttons showing checkmarks for completed categories."""
    status_icon = "✅ " if "status_count" in user_data else ""
    ooc_icon = "✅ " if "ooc_count" in user_data else ""
    nww_icon = "✅ " if "nww_count" in user_data else ""
    others_icon = "✅ " if "others_count" in user_data else ""

    keyboard = [
        [f"{status_icon}On Status", f"{ooc_icon}Out of Camp"],
        [f"{nww_icon}Currently Not With Wing", f"{others_icon}Others"],
        ["✅ DONE (Generate Report)"],
        ["↩️ Back", "❌ Cancel"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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

async def start_adhoc_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["is_arrival"] = False
    return await start_adhoc(update, context)

async def start_adhoc_arrival(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["is_arrival"] = True
    return await start_adhoc(update, context)

async def start_adhoc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    total_steps = 2 if context.user_data.get("is_arrival") else 3
    await update.message.reply_text(
        f"1/{total_steps}: Send the **NAMES** (one per line):",
        parse_mode="Markdown",
        reply_markup=STEP1_MENU,
    )
    return ADHOC_NAMES

async def get_adhoc_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_names = parse_raw_names(update.message.text)
    context.user_data["adhoc_raw_names"] = raw_names
    is_arrival = context.user_data.get("is_arrival", False)

    if is_arrival:
        await update.message.reply_text(
            "2/2: Send **ARRIVAL LOCATION**:",
            parse_mode="Markdown",
            reply_markup=LOC_NAV_MENU,
        )
        return ADHOC_TO
    else:
        await update.message.reply_text(
            "2/3: Send **LOCATION A** (Starting location):",
            parse_mode="Markdown",
            reply_markup=LOC_NAV_MENU,
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
        reply_markup=LOC_NAV_MENU,
    )
    return ADHOC_TO

async def back_to_adhoc_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("adhoc_from", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*Current Location A:* {current}\n\nSend **LOCATION A**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return ADHOC_FROM

async def back_from_adhoc_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Routes the back button dynamically depending on if it's an Arrival or Departure."""
    if context.user_data.get("is_arrival", False):
        return await back_to_adhoc_names(update, context)
    else:
        return await back_to_adhoc_from(update, context)

async def get_adhoc_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    to_loc = update.message.text.strip().upper()
    raw_names = context.user_data.get("adhoc_raw_names", [])
    
    current_time = datetime.now(SGT).strftime("%H%M")
    formatted_names = format_numbered_list(raw_names)

    if context.user_data.get("is_arrival", False):
        movement_text = f"Arrival at {to_loc} @ {current_time}H"
    else:
        from_loc = context.user_data.get("adhoc_from", "")
        movement_text = f"Movement from {from_loc} to {to_loc} @ {current_time}H"

    report = (
        "AD HOC MOVEMENT REPORT\n\n"
        f"{formatted_names}\n\n"
        f"{movement_text}"
    )

    await update.message.reply_text(f"```\n{report}\n```", parse_mode="Markdown")

    context.user_data.clear()
    await update.message.reply_text("Tap below for another:", reply_markup=MAIN_MENU)
    return ConversationHandler.END

# -------------------------------------------------------------------
# FLIGHT MOVEMENT REPORT FLOW
# -------------------------------------------------------------------

async def start_flight_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["is_arrival"] = False
    return await start_flight(update, context)

async def start_flight_arrival(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["is_arrival"] = True
    return await start_flight(update, context)

async def start_flight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    total_steps = 4 if context.user_data.get("is_arrival") else 5
    await update.message.reply_text(
        f"1/{total_steps}: Select Flight (ALPHA, BRAVO, or CHARLIE):", reply_markup=FLIGHT_CHOICE_MENU
    )
    return FLIGHT_SELECT

async def get_flight_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_name"] = update.message.text.strip().upper()
    is_arrival = context.user_data.get("is_arrival", False)

    if is_arrival:
        await update.message.reply_text(
            "2/4: Send **ARRIVAL LOCATION**:",
            parse_mode="Markdown",
            reply_markup=LOC_NAV_MENU,
        )
        return FLIGHT_TO
    else:
        await update.message.reply_text(
            "2/5: Send **LOCATION A** (Starting location):",
            parse_mode="Markdown",
            reply_markup=LOC_NAV_MENU,
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
        "3/5: Send **LOCATION B** (Destination):",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return FLIGHT_TO

async def back_to_flight_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_from", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*Current Location A:* {current}\n\nSend **LOCATION A**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return FLIGHT_FROM

async def back_from_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Routes the back button dynamically depending on if it's an Arrival or Departure."""
    if context.user_data.get("is_arrival", False):
        return await back_to_flight_select(update, context)
    else:
        return await back_to_flight_from(update, context)

async def get_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_to"] = update.message.text.strip().upper()
    is_arrival = context.user_data.get("is_arrival", False)
    step = "3/4" if is_arrival else "4/5"

    await update.message.reply_text(
        f"{step}: Send **TOTAL STRENGTH** (e.g., 37):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_TOTAL

async def back_to_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_to", "None")
    is_arrival = context.user_data.get("is_arrival", False)
    step = "2" if is_arrival else "3"
    loc_label = "ARRIVAL LOCATION" if is_arrival else "LOCATION B"

    await update.message.reply_text(
        f"Going back to Step {step}.\n\n*Current {loc_label}:* {current}\n\nSend **{loc_label}**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return FLIGHT_TO

async def get_flight_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_total"] = update.message.text.strip()
    is_arrival = context.user_data.get("is_arrival", False)
    step = "4/4" if is_arrival else "5/5"

    await update.message.reply_text(
        f"{step}: Send **CURRENT STRENGTH** (e.g., 37):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_CURRENT

async def back_to_flight_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_total", "None")
    is_arrival = context.user_data.get("is_arrival", False)
    step = "3" if is_arrival else "4"

    await update.message.reply_text(
        f"Going back to Step {step}.\n\n*Current Total Strength:* {current}\n\nSend **TOTAL STRENGTH**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FLIGHT_TOTAL

async def get_flight_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_current"] = update.message.text.strip()
    return await show_category_menu(update, context)

async def show_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the button options for status breakdown via Reply Keyboard."""
    reply_markup = get_category_keyboard(context.user_data)
    text = "Select categories to add personnel, or tap **✅ DONE** if completed:"
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    return FLIGHT_CATEGORY_MENU

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles text button clicks from the category menu."""
    choice = update.message.text

    if "On Status" in choice:
        raw = context.user_data.get("status_raw", "")
        msg = "Send **ON STATUS** personnel (Rank, Name & Reason, one per line) or type 'NIL':"
        if raw:
            msg = f"Current Input:\n```\n{raw}\n```\nSend updated **ON STATUS** personnel:"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=NAV_MENU)
        return FLIGHT_ENTER_STATUS

    elif "Out of Camp" in choice:
        raw = context.user_data.get("ooc_raw", "")
        msg = "Send **OUT OF CAMP** personnel (Rank, Name & Reason, one per line) or type 'NIL':"
        if raw:
            msg = f"Current Input:\n```\n{raw}\n```\nSend updated **OUT OF CAMP** personnel:"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=NAV_MENU)
        return FLIGHT_ENTER_OOC

    elif "Not With Wing" in choice:
        raw = context.user_data.get("nww_raw", "")
        msg = "Send **CURRENTLY NOT WITH WING** personnel (one per line) or type 'NIL':"
        if raw:
            msg = f"Current Input:\n```\n{raw}\n```\nSend updated **CURRENTLY NOT WITH WING** personnel:"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=NAV_MENU)
        return FLIGHT_ENTER_NWW

    elif "Others" in choice:
        raw = context.user_data.get("others_raw", "")
        msg = "Send **OTHERS** remarks/personnel or type 'NIL':"
        if raw:
            msg = f"Current Input:\n```\n{raw}\n```\nSend updated **OTHERS** remarks:"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=NAV_MENU)
        return FLIGHT_ENTER_OTHERS

    elif "DONE" in choice:
        now = datetime.now(SGT)
        caa_time = now.strftime("%H%MH %d%m%y")

        flight_name = context.user_data.get("flight_name", "")
        to_loc = context.user_data.get("flight_to", "")
        is_arrival = context.user_data.get("is_arrival", False)

        if is_arrival:
            movement_text = f"Arrival at {to_loc}"
        else:
            from_loc = context.user_data.get("flight_from", "")
            movement_text = f"Movement from {from_loc} to {to_loc}"

        total_str = context.user_data.get("flight_total", "0")
        curr_str = context.user_data.get("flight_current", "0")

        status_count = context.user_data.get("status_count", "00")
        status_list = context.user_data.get("status_list", "")
        ooc_count = context.user_data.get("ooc_count", "00")
        ooc_list = context.user_data.get("ooc_list", "")
        nww_count = context.user_data.get("nww_count", "00")
        nww_list = context.user_data.get("nww_list", "")
        others_count = context.user_data.get("others_count", "00")
        others_list = context.user_data.get("others_list", "")

        report_lines = [
            "MOVEMENT REPORT",
            "",
            f"{flight_name} FLIGHT",
            "",
            f"CAA: {caa_time}",
            "",
            movement_text,
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

async def receive_status_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["status_raw"] = text
    context.user_data["status_count"] = count_str
    context.user_data["status_list"] = formatted_list
    return await show_category_menu(update, context)

async def receive_ooc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["ooc_raw"] = text
    context.user_data["ooc_count"] = count_str
    context.user_data["ooc_list"] = formatted_list
    return await show_category_menu(update, context)

async def receive_nww_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["nww_raw"] = text
    context.user_data["nww_count"] = count_str
    context.user_data["nww_list"] = formatted_list
    return await show_category_menu(update, context)

async def receive_others_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    count_str, formatted_list = format_status_list(text)
    context.user_data["others_raw"] = text
    context.user_data["others_count"] = count_str
    context.user_data["others_list"] = formatted_list
    return await show_category_menu(update, context)

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
            MessageHandler(filters.Regex("^🚨 Ad Hoc$"), start_adhoc_departure),
            MessageHandler(filters.Regex("^🚨 Ad Hoc \(Arrival\)$"), start_adhoc_arrival),
            MessageHandler(filters.Regex("^✈️ Flight Movement$"), start_flight_departure),
            MessageHandler(filters.Regex("^✈️ Flight \(Arrival\)$"), start_flight_arrival),
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
            MessageHandler(filters.Regex("^↩️ Back$"), back_from_adhoc_to),
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
            MessageHandler(filters.Regex("^↩️ Back$"), back_from_flight_to),
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
        FLIGHT_CATEGORY_MENU: [
            MessageHandler(filters.Regex("(?i)On Status|Out of Camp|Not With Wing|Others|DONE"), handle_category_selection),
            MessageHandler(filters.Regex("^↩️ Back$"), back_to_flight_total),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        ],
        FLIGHT_ENTER_STATUS: [
            MessageHandler(filters.Regex("^↩️ Back$"), show_category_menu),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_status_input),
        ],
        FLIGHT_ENTER_OOC: [
            MessageHandler(filters.Regex("^↩️ Back$"), show_category_menu),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ooc_input),
        ],
        FLIGHT_ENTER_NWW: [
            MessageHandler(filters.Regex("^↩️ Back$"), show_category_menu),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_nww_input),
        ],
        FLIGHT_ENTER_OTHERS: [
            MessageHandler(filters.Regex("^↩️ Back$"), show_category_menu),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_others_input),
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
            # 'async with' guarantees a fresh connection and clean teardown per message
            async with telegram_app:
                update = Update.de_json(request.get_json(force=True), telegram_app.bot)
                await telegram_app.process_update(update)

        try:
            # Create a fresh event loop for this specific Vercel invocation
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(process())
        except Exception as e:
            print(f"Error processing update: {e}")
            
        return "OK", 200

    return "Bot is active!", 200