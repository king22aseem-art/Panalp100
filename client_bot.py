import asyncio, os, sqlite3, sys
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler

TOKEN = sys.argv[1]  # panel bot ye khud bhejta hai
OWNER_ID = sys.argv[2] if len(sys.argv) > 2 else "0"
INTERVAL = 60  # seconds
BOT_ID = TOKEN.split(":")[0]
FILE = f"chats_{BOT_ID}.txt"


def load():
    """chat_id -> admin_id (kis admin ka user hai)"""
    d = {}
    if os.path.exists(FILE):
        for line in open(FILE).read().splitlines():
            p = line.split()
            if p:
                d[p[0]] = p[1] if len(p) > 1 else OWNER_ID
    return d


def save(d):
    open(FILE, "w").write("\n".join(f"{k} {v}" for k, v in d.items()))


def valid_admin(a):
    if a == OWNER_ID:
        return True
    try:
        db = sqlite3.connect("bots.db")
        r = db.execute("SELECT 1 FROM admins WHERE id=?", (int(a),)).fetchone()
        db.close()
        return r is not None
    except Exception:
        return False


def admin_ids():
    """Owner + saare admins (string ids)"""
    ids = {OWNER_ID}
    try:
        db = sqlite3.connect("bots.db")
        ids.update(str(r[0]) for r in db.execute("SELECT id FROM admins"))
        db.close()
    except Exception:
        pass
    return ids


def active_admins():
    """Kin admins ne is bot ko abhi START rakha hai (panel ke /on se)"""
    try:
        db = sqlite3.connect("bots.db")
        r = {x[0] for x in db.execute("SELECT admin FROM running WHERE bot=?", (BOT_ID,))}
        db.close()
        return r
    except Exception:
        return set()


def get_msg(admin):
    """Har admin ka apna message. Kisi doosre admin ka message kabhi nahi jata."""
    f = f"msg_{BOT_ID}_{admin}.txt"
    if os.path.exists(f):
        return open(f, encoding="utf-8").read()
    old = f"msg_{BOT_ID}.txt"  # purana message sirf owner ke liye
    if admin == OWNER_ID and os.path.exists(old):
        return open(old, encoding="utf-8").read()
    return None


async def start(update, ctx):
    user = update.effective_user
    if not user:
        return
    uid = str(user.id)
    chats = load()
    arg = ctx.args[0] if ctx.args else ""
    if uid in admin_ids():
        admin = uid  # admin khud start kare to usi ka message milega
    elif arg.isdigit() and valid_admin(arg):
        admin = arg  # admin ke link se aaya
    else:
        admin = chats.get(uid, OWNER_ID)
    try:
        await ctx.bot.send_message(user.id, "✅")
    except Forbidden:
        link = f"https://t.me/{ctx.bot.username}?start={admin}"
        return await update.message.reply_text(f"Pehle bot ko private mein start karo:\n{link}")
    chats[uid] = admin
    save(chats)


async def sender(app):
    while True:
        await asyncio.sleep(INTERVAL)
        admins = admin_ids()
        active = active_admins()
        for cid, admin in load().items():
            if cid in admins:
                admin = cid  # admin ka apna chat: usi ka message
            if admin not in active:
                continue  # is admin ne START nahi kiya (ya STOP kar diya)
            msg = get_msg(admin)
            if not msg:
                continue
            try:
                await app.bot.send_message(int(cid), msg)
            except Exception as e:
                print(cid, e)


async def post_init(app):
    app.bot_data["task"] = asyncio.create_task(sender(app))


app = Application.builder().token(TOKEN).post_init(post_init).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()


