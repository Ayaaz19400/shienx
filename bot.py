import os
import asyncio
import threading
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton
)

# ================= CONFIGURATION =================
# 1. API KEYS
API_ID = 10198031
API_HASH = "9829e7537152e651aec7f8c69ec57e91"
# Get Token from Secrets (Environment Variables) or hardcode if testing
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8307449726:AAG5yhE7xYwy1y9ANqeT9KVim-0jgWyf5mQ")

# 2. ADMIN & CHANNEL
ADMIN_ID = 1455619072   

# ⚠️ IMPORTANT: Use your PUBLIC Channel Username (with the @)
# This prevents "Peer ID Invalid" errors on Replit
STOCK_CHANNEL_ID = "@allubfifi" 

# 3. PAYMENT DETAILS
PAYMENT_LINK = "https://aaluu.pages.dev/"
PAYMENT_UPI = "techamit2312003@okaxis"

# 4. PRICING RULES
PRICING = {
    "1000": { 1: 20, 5: 100, 10: 190, 20: 380 },
    "4000": { 1: 50, 5: 250, 10: 490, 20: 970 },
    "default": { 1: 50 }
}

# ================= FLASK SERVER (KEEPS BOT ALIVE) =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Replit Shop Bot is Alive!"

def run_web_server():
    # Replit standard port is 8080
    app.run(host='0.0.0.0', port=8080)

# ================= BOT CLIENT =================
# in_memory=True avoids disk permission issues
bot = Client("shop_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ================= DATABASE LOGIC (SEARCH MODE) =================
async def check_connection():
    print(f"🔌 Connecting to {STOCK_CHANNEL_ID}...")
    try:
        chat = await bot.get_chat(STOCK_CHANNEL_ID)
        print(f"✅ CONNECTED to: {chat.title} (ID: {chat.id})")
        return True
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        return False

async def get_stock_counts():
    counts = {}
    try:
        # 🔥 Optimization: Search instead of scanning history to save RAM
        async for msg in bot.search_messages(STOCK_CHANNEL_ID, query="AVAILABLE", limit=50):
            try:
                # Format: AVAILABLE 1000 CODE
                parts = msg.text.split()
                if len(parts) >= 2:
                    price = parts[1]
                    counts[price] = counts.get(price, 0) + 1
            except: pass
        return dict(sorted(counts.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 0))
    except Exception as e:
        return str(e)

async def fetch_codes_bulk(price_type, quantity):
    codes_found = []
    msgs_to_edit = []
    try:
        # Specific search for the price type
        query_text = f"AVAILABLE {price_type}"
        async for msg in bot.search_messages(STOCK_CHANNEL_ID, query=query_text, limit=quantity+5):
            if len(codes_found) >= quantity: break
            parts = msg.text.split()
            # Double check price match
            if len(parts) >= 3 and parts[1] == str(price_type):
                code = parts[2]
                codes_found.append(code)
                msgs_to_edit.append(msg)

        if len(codes_found) == quantity:
            for i, msg in enumerate(msgs_to_edit):
                await bot.edit_message_text(STOCK_CHANNEL_ID, msg.id, f"❌ SOLD {price_type} {codes_found[i]}")
            return codes_found
    except: pass
    return None

async def mark_order_complete(msg_id, status_text):
    try: await bot.edit_message_text(STOCK_CHANNEL_ID, msg_id, status_text)
    except: pass

async def get_pending_orders():
    orders = []
    try:
        async for msg in bot.search_messages(STOCK_CHANNEL_ID, query="ORDER", limit=20):
            parts = msg.text.split()
            if len(parts) >= 5:
                orders.append({"msg_id": msg.id, "user_id": parts[1], "type": parts[2], "qty": parts[3], "cost": parts[4]})
        return orders
    except: return []

# ================= USER UI =================
@bot.on_message(filters.command("start"))
async def start(c, m):
    # Auto-Heal connection on start
    await check_connection()
    kb = ReplyKeyboardMarkup([[KeyboardButton("🛒 Buy Vouchers"), KeyboardButton("📦 Check Stock")], [KeyboardButton("🆘 Support")]], resize_keyboard=True)
    await m.reply_text("👋 **Welcome to the Store!**", reply_markup=kb)

@bot.on_message(filters.regex("🛒 Buy Vouchers"))
async def buy(c, m):
    result = await get_stock_counts()
    
    if isinstance(result, str): 
        return await m.reply_text(f"❌ **DB Error:** {result}")
    if not result:
        return await m.reply_text("❌ Out of Stock.")
    
    counts = result
    btns = []
    for p, c in counts.items(): btns.append([InlineKeyboardButton(f"₹{p} (Stock: {c})", callback_data=f"sel_{p}")])
    await m.reply_text("🛍️ **Select Voucher:**", reply_markup=InlineKeyboardMarkup(btns))

@bot.on_message(filters.regex("📦 Check Stock"))
async def stock(c, m):
    result = await get_stock_counts()
    if isinstance(result, str): return await m.reply_text(f"❌ Error: {result}")
    
    counts = result
    if not counts: return await m.reply_text("❌ Out of Stock")
    
    text = "📦 **Stock:**\n"
    for p, c in counts.items(): text += f"• ₹{p}: {c}\n"
    await m.reply_text(text)

@bot.on_message(filters.regex("🆘 Support"))
async def supp(c, m): await m.reply_text("@animeverse23_requesting_bot")

# ================= CALLBACKS =================
@bot.on_callback_query()
async def cb(c, q):
    d = q.data
    if d.startswith("sel_"):
        v = d.split("_")[1]
        opts = PRICING.get(v, PRICING["default"])
        
        result = await get_stock_counts()
        if isinstance(result, str) or not result:
            return await q.answer("Stock Error!", show_alert=True)
            
        counts = result
        real_stock = counts.get(v, 0)
        
        btns = []
        for qty, price in opts.items():
            if real_stock >= qty: btns.append([InlineKeyboardButton(f"{qty}x -> ₹{price}", callback_data=f"pay_{v}_{qty}_{price}")])
        if not btns: return await q.answer("Not enough stock!", show_alert=True)
        await q.edit_message_text(f"🔢 Quantity for ₹{v}:", reply_markup=InlineKeyboardMarkup(btns))

    elif d.startswith("pay_"):
        _, v, qty, cost = d.split("_")
        btns = [
            [InlineKeyboardButton("🌐 Web Link", url=PAYMENT_LINK)],
            [InlineKeyboardButton("💳 UPI ID", callback_data=f"upi_{cost}")],
            [InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid_{v}_{qty}_{cost}")]
        ]
        await q.edit_message_text(f"💳 **Pay ₹{cost}**", reply_markup=InlineKeyboardMarkup(btns))

    elif d.startswith("upi_"):
        await q.answer(PAYMENT_UPI, show_alert=True)
        await q.message.reply_text(f"`{PAYMENT_UPI}`")

    elif d.startswith("paid_"):
        _, v, qty, cost = d.split("_")
        uid = q.from_user.id
        try:
            s_msg = await bot.send_message(STOCK_CHANNEL_ID, f"ORDER {uid} {v} {qty} {cost}")
            await bot.send_message(ADMIN_ID, f"⚠️ **Order!**\nUser: `{uid}`\nAmt: ₹{cost}\n/verify_{s_msg.id}")
            await q.edit_message_text("✅ Sent! Wait for approval.")
        except Exception as e: await q.answer(f"DB Error: {e}", show_alert=True)

    elif d.startswith("ok_"):
        _, mid, uid, v, qty = d.split("_")
        codes = await fetch_codes_bulk(v, int(qty))
        if codes:
            await mark_order_complete(int(mid), f"✅ COMPLETED {uid} {v} {qty}")
            code_txt = "\n".join([f"`{x}`" for x in codes])
            try: await bot.send_message(int(uid), f"🎉 **Approved!**\n\n{code_txt}")
            except: pass
            await q.edit_message_text("✅ Approved.")
        else: await q.answer("Stock Gone!", show_alert=True)

    elif d.startswith("no_"):
        _, mid, uid = d.split("_")
        await mark_order_complete(int(mid), f"❌ REJECTED {uid}")
        try: await bot.send_message(int(uid), "❌ Rejected.")
        except: pass
        await q.edit_message_text("Rejected.")

# ================= ADMIN COMMANDS =================
async def add_stock(m, price):
    try:
        code = m.text.split()[1]
        await bot.send_message(STOCK_CHANNEL_ID, f"AVAILABLE {price} {code}")
        await m.reply_text(f"✅ Added.")
    except Exception as e: await m.reply_text(f"Error: {e}")

@bot.on_message(filters.command("add500") & filters.user(ADMIN_ID))
async def a500(c, m): await add_stock(m, "500")
@bot.on_message(filters.command("add1000") & filters.user(ADMIN_ID))
async def a1000(c, m): await add_stock(m, "1000")
@bot.on_message(filters.command("add2000") & filters.user(ADMIN_ID))
async def a2000(c, m): await add_stock(m, "2000")
@bot.on_message(filters.command("add4000") & filters.user(ADMIN_ID))
async def a4000(c, m): await add_stock(m, "4000")

@bot.on_message(filters.command("stock") & filters.user(ADMIN_ID))
async def adm_stock(c, m): await stock(c, m)

@bot.on_message(filters.command("pending") & filters.user(ADMIN_ID))
async def adm_pending(c, m):
    orders = await get_pending_orders()
    if not orders: return await m.reply_text("✅ No pending.")
    text = "⏳ **Pending:**\n"
    for o in orders: text += f"User: `{o['user_id']}` | ₹{o['cost']} | /verify_{o['msg_id']}\n"
    await m.reply_text(text)

@bot.on_message(filters.regex(r"^/verify_(\d+)") & filters.user(ADMIN_ID))
async def verify(c, m):
    msg_id = int(m.matches[0].group(1))
    try:
        t_msg = await bot.get_messages(STOCK_CHANNEL_ID, msg_id)
        parts = t_msg.text.split()
        uid, v, qty, cost = int(parts[1]), parts[2], int(parts[3]), parts[4]
        btns = [[InlineKeyboardButton("✅ Approve", callback_data=f"ok_{msg_id}_{uid}_{v}_{qty}"), InlineKeyboardButton("❌ Reject", callback_data=f"no_{msg_id}_{uid}")]]
        await m.reply_text(f"Verify:\nAmount: ₹{cost}", reply_markup=InlineKeyboardMarkup(btns))
    except: await m.reply_text("Order not found.")

# ================= RUNNER =================
def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    # Start Flask Server in background
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    print("🚀 Starting Replit Bot...")
    bot.run()
