import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

# States
NAMES, FROM_LOC, TO_LOC = range(3)

# Keyboards
MAIN_MENU = ReplyKeyboardMarkup([["📝 Movement Report"]], resize_keyboard=True)
# Menu for Step 1 (Cancel only)
STEP1_MENU = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
# Menu for Steps 2 & 3 (Cancel + Back)
NAV_MENU = ReplyKeyboardMarkup([["↩️ Back", "❌ Cancel"]], resize_keyboard=True)


def format_numbered_list(text: str) -> str:
    """Splits input lines, converts to uppercase, and adds numbering (1., 2., ...)."""
    lines = [line.strip().upper() for line in text.strip().split("\n") if line.strip()]
    return "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ready! Tap below to start:", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 1: Ask for Names."""
    await update.message.reply_text(
        "1/3: Send the **NAMES** (one per line):",
        parse_mode="Markdown",
        reply_markup=STEP1_MENU,
    )
    return NAMES


async def get_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 1 -> Step 2: Format & store names, ask for Location A."""
    formatted_names = format_numbered_list(update.message.text)
    context.user_data["names"] = formatted_names

    await update.message.reply_text(
        "2/3: Send **LOCATION A** (Starting location):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FROM_LOC


async def back_to_names(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 2 -> Step 1: Go back to edit Names."""
    # Show current saved names so user can edit/re-send
    current = context.user_data.get("names", "None")
    await update.message.reply_text(
        f"Going back to Step 1.\n\n*Current Names:*\n{current}\n\nSend the updated **NAMES**:",
        parse_mode="Markdown",
        reply_markup=STEP1_MENU,
    )
    return NAMES


async def get_from_loc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 2 -> Step 3: Store Location A in uppercase, ask for Location B."""
    context.user_data["from_loc"] = update.message.text.strip().upper()

    await update.message.reply_text(
        "3/3: Send **LOCATION B** (Destination):",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return TO_LOC


async def back_to_from_loc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 3 -> Step 2: Go back to edit Location A."""
    current = context.user_data.get("from_loc", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*Current Location A:* {current}\n\nSend **LOCATION A**:",
        parse_mode="Markdown",
        reply_markup=NAV_MENU,
    )
    return FROM_LOC


async def get_to_loc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 3 -> Finish: Format, print output, and reset."""
    context.user_data["to_loc"] = update.message.text.strip().upper()
    current_time = datetime.now().strftime("%H%M")

    report = (
        "MOVEMENT REPORT\n\n"
        f"{context.user_data['names']}\n\n"
        f"MOVEMENT FROM {context.user_data['from_loc']} TO {context.user_data['to_loc']} @ {current_time}H"
    )

    await update.message.reply_text(f"```\n{report}\n```", parse_mode="Markdown")

    context.user_data.clear()
    await update.message.reply_text("Tap below for another:", reply_markup=MAIN_MENU)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN is not set in the .env file!")

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^📝 Movement Report$"), start_report),
        ],
        states={
            NAMES: [
                MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
                MessageHandler(filters.TEXT, get_names),
            ],
            FROM_LOC: [
                MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
                MessageHandler(filters.Regex("^↩️ Back$"), back_to_names),
                MessageHandler(filters.TEXT, get_from_loc),
            ],
            TO_LOC: [
                MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
                MessageHandler(filters.Regex("^↩️ Back$"), back_to_from_loc),
                MessageHandler(filters.TEXT, get_to_loc),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            MessageHandler(filters.Regex("^📝 Movement Report$"), start_report),
        ],
    )

    app.add_handler(conv_handler)
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()