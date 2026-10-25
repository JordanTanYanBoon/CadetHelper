import os
import asyncio
from datetime import datetime
import zoneinfo
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
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

# -------------------------------------------------------------------
# Neon PostgreSQL Database Configuration
# -------------------------------------------------------------------
db_url = os.getenv("DATABASE_URL", "")
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

class AdHocRecord(db.Model):
    __tablename__ = "adhoc_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False, index=True)
    raw_names = db.Column(db.Text, nullable=True)
    from_location = db.Column(db.String(100), nullable=True)
    to_location = db.Column(db.String(100), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SGT), onupdate=lambda: datetime.now(SGT))

class FlightRecord(db.Model):
    __tablename__ = "flight_records"

    id = db.Column(db.Integer, primary_key=True)
    flight_name = db.Column(db.String(50), primary_key=True) # ALPHA, BRAVO, or CHARLIE
    from_location = db.Column(db.String(100), nullable=True)
    to_location = db.Column(db.String(100), nullable=True)
    total_strength = db.Column(db.String(10), nullable=True)
    current_strength = db.Column(db.String(10), nullable=True)
    status_count = db.Column(db.String(10), nullable=True)
    status_list = db.Column(db.Text, nullable=True)
    status_raw = db.Column(db.Text, nullable=True)
    ooc_count = db.Column(db.String(10), nullable=True)
    ooc_list = db.Column(db.Text, nullable=True)
    ooc_raw = db.Column(db.Text, nullable=True)
    nww_count = db.Column(db.String(10), nullable=True)
    nww_list = db.Column(db.Text, nullable=True)
    nww_raw = db.Column(db.Text, nullable=True)
    others_count = db.Column(db.String(10), nullable=True)
    others_list = db.Column(db.Text, nullable=True)
    others_raw = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(SGT), onupdate=lambda: datetime.now(SGT))

with app.app_context():
    db.create_all()

# -------------------------------------------------------------------
# Database Helpers
# -------------------------------------------------------------------

def save_adhoc_departure(user_id: int, raw_names: list[str], from_loc: str, to_loc: str):
    record = AdHocRecord.query.filter_by(user_id=user_id).first()
    if not record:
        record = AdHocRecord(user_id=user_id)
        db.session.add(record)
    record.raw_names = "\n".join(raw_names)
    record.from_location = from_loc
    record.to_location = to_loc
    db.session.commit()

def get_adhoc_last_record(user_id: int) -> AdHocRecord:
    return AdHocRecord.query.filter_by(user_id=user_id).first()

def save_flight_departure(data: dict):
    flight_name = data.get("flight_name")
    record = FlightRecord.query.filter_by(flight_name=flight_name).first()
    if not record:
        record = FlightRecord(flight_name=flight_name)
        db.session.add(record)
    
    record.from_location = data.get("flight_from", "")
    record.to_location = data.get("flight_to", "")
    record.total_strength = data.get("flight_total", "0")
    record.current_strength = data.get("flight_current", "0")
    record.status_count = data.get("status_count", "00")
    record.status_list = data.get("status_list", "")
    record.status_raw = data.get("status_raw", "")
    record.ooc_count = data.get("ooc_count", "00")
    record.ooc_list = data.get("ooc_list", "")
    record.ooc_raw = data.get("ooc_raw", "")
    record.nww_count = data.get("nww_count", "00")
    record.nww_list = data.get("nww_list", "")
    record.nww_raw = data.get("nww_raw", "")
    record.others_count = data.get("others_count", "00")
    record.others_list = data.get("others_list", "")
    record.others_raw = data.get("others_raw", "")
    db.session.commit()

def get_flight_last_record(flight_name: str) -> FlightRecord:
    return FlightRecord.query.filter_by(flight_name=flight_name).first()


# -------------------------------------------------------------------
# Conversation States & Keyboards
# -------------------------------------------------------------------

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
    # Flight Notes States
    FLIGHT_NOTES_STATE,
) = range(15)

MAIN_MENU = ReplyKeyboardMarkup([["📝 Movement Report", "📋 Flight Notes"]], resize_keyboard=True)

TYPE_MENU = ReplyKeyboardMarkup(
    [
        ["🚨 Ad Hoc", "🚨 Ad Hoc (Arrival)"],
        ["✈️ Flight Movement", "✈️ Flight (Arrival)"],
        ["❌ Cancel"]
    ], 
    resize_keyboard=True
)

FLIGHT_NOTES_MENU = ReplyKeyboardMarkup(
    [["🛏️ Bravo Bunk Standardisation"], ["❌ Cancel"]], resize_keyboard=True
)

FLIGHT_CHOICE_MENU = ReplyKeyboardMarkup(
    [["ALPHA", "BRAVO", "CHARLIE"], ["↩️ Back", "❌ Cancel"]], resize_keyboard=True
)

STEP1_MENU = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
NAV_MENU = ReplyKeyboardMarkup([["↩️ Back", "❌ Cancel"]], resize_keyboard=True)

LOC_NAV_MENU = ReplyKeyboardMarkup(
    [
        ["AIR WINGLINE", "DHA", "CA2"],
        ["SAFTI MC", "SAFTI PS", "SAFTI GAURDROOM"],
        ["RUBBISH CHUTE"],
        ["↩️ Back", "❌ Cancel"]
    ], 
    resize_keyboard=True
)

BUNK_STANDARDISATION_TEXT = """Bunk standardisation 
Hang clothes closet
- pillowcase on top, handle facing out and the zip zipped close
- Orca attire flushed to the right, follow last week one
- 1x smart 4 attire flushed to the left, facing the orca. Follow orca way of hanging, shirt dont button only velcro.
- Unused hangers keep in duffel
- Extra no 4 attire fold with the name tag out and put at left side, pants behind. If unsure this is basically the SLT PDF way.

Below the closet top most drawers
- where all your RR, WW, socks and underwear are, follow last week one. If have more than one is ok, but must at least have one.

Middle and bottom drawers
- Middle empty
- Bottom put personal stuff like your attires that are not RR WW and no 4, but must be neat

Field pack compartment 
- top part put LBS, everything strapped and buckled, front buckle facing outwards (basically the toggle rope part at the inside)
- Bottom part from left to right: assault bag, field pack, laptop bag, all facing left. 

Towel racks
- towel tag at the left side at the inner side of the towel when placed at the rack.
- Beside towel rack is all the headgears, from top to bottom: helmet, jockey, helmet, jockey. 

Compartment on top of table
- Bottom part all dry toiletries and laundry stuff, flushed to right side neatly. Left side any miscellaneous stuff yall have.
- Middle part comms bag on the left, journal stuff to the right
- Top part empty
- If got any food placed in here please put in duffel during SBA

Compartment on top of rifle locker
- Top part empty 
- Middle and bottom part one person take one part, put wet toiletries stuff like toothbrush toothpaste shaver and whatever flush to right side.

Other stuff in room
- bucket upside down flushed towards the rifle locker, handle facing straight outwards 
- Duffel bag at the head of the bed, name tag face outward, everything zipped and buckled
- Shoes starting from the foot of the bed, boots with shoelaces tucked in, admin, non admin running shoes, book out shoe, slippers. If anything shoe dont have one just flush the rest toward the foot of the bed. 
- Rubbish bin in front of the rifle locker with pedal facing outwards
- Tables empty, chairs hang, beds neat, book out bag at the foot of the bed like last week.
- Clean mosquito nets and blinds

Last week’s SBA notes

Toilet
Leave fans on to dry
Top of the showers
Sinks last to be cleaned
No hair in drain, open drain and throw inside
Scrub soap stains on door
Open washing machine to dry
Clean power stain on washing machine 
Clean under washing machine 
Washing machine drain clogged
Dirt at washing machine area

Common Area
loud hailer
notice board
cabinets 
tables and hangar
hose reel
All ledges
all accessible surfaces"""

def parse_raw_names(text: str) -> list[str]:
    return [line.strip().upper() for line in text.strip().split("\n") if line.strip()]

def format_numbered_list(names: list[str]) -> str:
    return "\n".join(f"{i+1}. {name}" for i, name in enumerate(names))

def format_status_list(text: str) -> tuple[str, str]:
    cleaned = text.strip()
    if cleaned.upper() in ["NIL", "NONE", "0", "NO", "-"]:
        return "00", ""

    lines = [line.strip().upper() for line in cleaned.split("\n") if line.strip()]
    count_str = f"{len(lines):02d}"
    formatted_items = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))
    return count_str, formatted_items

def get_category_keyboard(user_data: dict) -> ReplyKeyboardMarkup:
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
    await update.message.reply_text(
        "Select the type of Movement Report:", reply_markup=TYPE_MENU
    )
    return REPORT_TYPE

async def start_flight_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Select Flight Notes option:", reply_markup=FLIGHT_NOTES_MENU
    )
    return FLIGHT_NOTES_STATE

async def send_bunk_standardisation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(BUNK_STANDARDISATION_TEXT, reply_markup=MAIN_MENU)
    return ConversationHandler.END

# -------------------------------------------------------------------
# AD HOC MOVEMENT REPORT FLOW
# -------------------------------------------------------------------

async def start_adhoc_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["is_arrival"] = False
    await update.message.reply_text(
        "1/3: Send the **NAMES** (one per line):",
        parse_mode="Markdown",
        reply_markup=STEP1_MENU,
    )
    return ADHOC_NAMES

async def start_adhoc_arrival(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["is_arrival"] = True
    user_id = update.effective_user.id
    record = get_adhoc_last_record(user_id)

    if record and record.raw_names:
        names_list = parse_raw_names(record.raw_names)
        context.user_data["adhoc_raw_names"] = names_list
        loc = record.to_location or "Destination"
        
        await update.message.reply_text(
            f"Fetched previous departure names ({len(names_list)} pax).\n"
            f"Send **ARRIVAL LOCATION** (Default from departure: {loc}):",
            parse_mode="Markdown",
            reply_markup=LOC_NAV_MENU,
        )
        return ADHOC_TO
    else:
        await update.message.reply_text(
            "No previous departure found.\n1/2: Send the **NAMES** (one per line):",
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
            "2/3: Send **STARTING LOCATION**:",
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
        "3/3: Send **Destination**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return ADHOC_TO

async def back_to_adhoc_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("adhoc_from", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*STARTING LOCATION:* {current}\n\nSend **STARTING LOCATION**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return ADHOC_FROM

async def back_from_adhoc_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("is_arrival", False):
        return await back_to_adhoc_names(update, context)
    else:
        return await back_to_adhoc_from(update, context)

async def get_adhoc_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    to_loc = update.message.text.strip().upper()
    raw_names = context.user_data.get("adhoc_raw_names", [])
    
    current_time = datetime.now(SGT).strftime("%H%M")
    formatted_names = format_numbered_list(raw_names)
    user_id = update.effective_user.id

    if context.user_data.get("is_arrival", False):
        movement_text = f"Arrival at {to_loc} @ {current_time}H"
    else:
        from_loc = context.user_data.get("adhoc_from", "")
        movement_text = f"Movement from {from_loc} to {to_loc} @ {current_time}H"
        # Save to database for next arrival lookup
        save_adhoc_departure(user_id, raw_names, from_loc, to_loc)

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
    total_steps = 2 if context.user_data.get("is_arrival") else 5
    await update.message.reply_text(
        f"1/{total_steps}: Select Flight (ALPHA, BRAVO, or CHARLIE):", reply_markup=FLIGHT_CHOICE_MENU
    )
    return FLIGHT_SELECT

async def get_flight_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flight_name = update.message.text.strip().upper()
    context.user_data["flight_name"] = flight_name
    is_arrival = context.user_data.get("is_arrival", False)

    if is_arrival:
        record = get_flight_last_record(flight_name)
        if record:
            context.user_data["flight_total"] = record.total_strength
            context.user_data["flight_current"] = record.current_strength
            context.user_data["status_count"] = record.status_count
            context.user_data["status_list"] = record.status_list
            context.user_data["status_raw"] = record.status_raw
            context.user_data["ooc_count"] = record.ooc_count
            context.user_data["ooc_list"] = record.ooc_list
            context.user_data["ooc_raw"] = record.ooc_raw
            context.user_data["nww_count"] = record.nww_count
            context.user_data["nww_list"] = record.nww_list
            context.user_data["nww_raw"] = record.nww_raw
            context.user_data["others_count"] = record.others_count
            context.user_data["others_list"] = record.others_list
            context.user_data["others_raw"] = record.others_raw

            dest = record.to_location or "Destination"
            await update.message.reply_text(
                f"Fetched latest movement data for {flight_name} Flight.\n"
                f"2/2: Send **ARRIVAL LOCATION** (Default from departure: {dest}):",
                parse_mode="Markdown",
                reply_markup=LOC_NAV_MENU,
            )
            return FLIGHT_TO
        else:
            await update.message.reply_text(
                f"No previous record for {flight_name} Flight. Proceeding with standard flow.\n"
                "2/4: Send **ARRIVAL LOCATION**:",
                parse_mode="Markdown",
                reply_markup=LOC_NAV_MENU,
            )
            return FLIGHT_TO
    else:
        await update.message.reply_text(
            "2/5: Send **STARTING LOCATION**:",
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
        "3/5: Send **ARRIVAL LOCATION**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return FLIGHT_TO

async def back_to_flight_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_from", "None")
    await update.message.reply_text(
        f"Going back to Step 2.\n\n*STARTING LOCATION:* {current}\n\nSend **STARTING LOCATION**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return FLIGHT_FROM

async def back_from_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("is_arrival", False):
        return await back_to_flight_select(update, context)
    else:
        return await back_to_flight_from(update, context)

async def get_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_to"] = update.message.text.strip().upper()
    is_arrival = context.user_data.get("is_arrival", False)

    if is_arrival:
        # Generate Arrival report immediately using pre-fetched database data
        now = datetime.now(SGT)
        caa_time = now.strftime("%H%MH %d%m%y")

        flight_name = context.user_data.get("flight_name", "")
        to_loc = context.user_data.get("flight_to", "")
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
            f"Arrival at {to_loc}",
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
    else:
        await update.message.reply_text(
            "4/5: Send **TOTAL STRENGTH** (e.g., 37):",
            parse_mode="Markdown",
            reply_markup=NAV_MENU,
        )
        return FLIGHT_TOTAL

async def back_to_flight_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = context.user_data.get("flight_to", "None")
    is_arrival = context.user_data.get("is_arrival", False)
    step = "2" if is_arrival else "3"

    await update.message.reply_text(
        f"Going back to Step {step}.\n\n*Current ARRIVAL LOCATION:* {current}\n\nSend **ARRIVAL LOCATION**:",
        parse_mode="Markdown",
        reply_markup=LOC_NAV_MENU,
    )
    return FLIGHT_TO

async def get_flight_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["flight_total"] = update.message.text.strip()
    await update.message.reply_text(
        "5/5: Send **CURRENT STRENGTH** (e.g., 37):",
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
    return await show_category_menu(update, context)

async def show_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = get_category_keyboard(context.user_data)
    text = "Select categories to add personnel, or tap **✅ DONE** if completed:"
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    return FLIGHT_CATEGORY_MENU

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        others_count = context.user_data.get("others_count", "00")
        others_list = context.user_data.get("others_list", "")

        # Save to database for next arrival lookup
        save_flight_departure(context.user_data)

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
        MessageHandler(filters.Regex("^📋 Flight Notes$"), start_flight_notes),
    ],
    states={
        REPORT_TYPE: [
            MessageHandler(filters.Regex("^🚨 Ad Hoc$"), start_adhoc_departure),
            MessageHandler(filters.Regex("^🚨 Ad Hoc \(Arrival\)$"), start_adhoc_arrival),
            MessageHandler(filters.Regex("^✈️ Flight Movement$"), start_flight_departure),
            MessageHandler(filters.Regex("^✈️ Flight \(Arrival\)$"), start_flight_arrival),
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
        ],
        FLIGHT_NOTES_STATE: [
            MessageHandler(filters.Regex("^🛏️ Bravo Bunk Standardisation$"), send_bunk_standardisation),
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
        MessageHandler(filters.Regex("^📋 Flight Notes$"), start_flight_notes),
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

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(process())
        except Exception as e:
            print(f"Error processing update: {e}")
            
        return "OK", 200

    return "Bot is active!", 200