import sqlite3, subprocess, sys
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

PANEL_TOKEN = "8961930793:AAEjGgq8KX152bIz3zqmxHsDprHB6UBDzhs"
OWNER_ID = 2007203426
CLIENT_SCRIPT = "client_bot.py"

db = sqlite3.connect("bots.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS bots(name TEXT PRIMARY KEY, token TEXT, active INTEGER DEFAULT 0)")
db.execute("CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY)")
db.execute("CREATE TABLE IF NOT EXISTS running(bot TEXT, admin TEXT, PRIMARY KEY(bot, admin))")
procs = {}


def running(name):
    p = procs.get(name)
    return p is not None and p.poll() is None


def start_bot(name):
    if not running(name):
        (token,) = db.execute("SELECT token FROM bots WHERE name=?", (name,)).fetchone()
        procs[name] = subprocess.Popen([sys.executable, CLIENT_SCRIPT, token, str(OWNER_ID)])
    db.execute("UPDATE bots SET active=1 WHERE name=?", (name,))
    db.commit()


def stop_bot(name):
    p = procs.pop(name, None)
    if p and p.poll() is None:
        p.terminate()
    db.execute("UPDATE bots SET active=0 WHERE name=?", (name,))
    db.commit()


def bot_id(name):
    (token,) = db.execute("SELECT token FROM bots WHERE name=?", (name,)).fetchone()
    return token.split(":")[0]


def is_active(name, admin_id):
    return db.execute("SELECT 1 FROM running WHERE bot=? AND admin=?", (bot_id(name), str(admin_id))).fetchone() is not None


def set_active(name, admin_id, on):
    """Har admin ka apna start/stop. Process tab tak chalta hai jab tak koi ek admin active hai."""
    bid = bot_id(name)
    if on:
        db.execute("INSERT OR IGNORE INTO running VALUES(?,?)", (bid, str(admin_id)))
        db.commit()
        start_bot(name)
    else:
        db.execute("DELETE FROM running WHERE bot=? AND admin=?", (bid, str(admin_id)))
        db.commit()
        if not db.execute("SELECT 1 FROM running WHERE bot=?", (bid,)).fetchone():
            stop_bot(name)


def force_off(name):
    db.execute("DELETE FROM running WHERE bot=?", (bot_id(name),))
    db.commit()
    stop_bot(name)


def status_for(uid):
    return "\n".join(f"{'🟢' if is_active(n, uid) else '🔴'} {n}" for n in names()) or "Koi bot nahi"


def names():
    return [r[0] for r in db.execute("SELECT name FROM bots")]


def is_admin(uid):
    return uid == OWNER_ID or db.execute("SELECT 1 FROM admins WHERE id=?", (uid,)).fetchone() is not None


def owner_only(fn):
    async def wrap(u: Update, c: ContextTypes.DEFAULT_TYPE):
        if u.effective_user.id == OWNER_ID:
            await fn(u, c)
    return wrap


def admin_only(fn):
    async def wrap(u: Update, c: ContextTypes.DEFAULT_TYPE):
        if is_admin(u.effective_user.id):
            await fn(u, c)
    return wrap


OWNER_USER = "@mafia_support2"


def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


MENU = InlineKeyboardMarkup([
    [btn("🟢 Start All", "m_on"), btn("🔴 Stop All", "m_off")],
    [btn("📋 List", "m_list"), btn("👥 Admins", "m_admins")],
    [btn("➕ Add Bot", "m_add"), btn("⚙️ Help", "m_help")],
])

ADMIN_MENU = InlineKeyboardMarkup([
    [btn("🟢 Start All", "m_on"), btn("🔴 Stop All", "m_off")],
    [btn("📋 List", "m_list"), InlineKeyboardButton(f"👑 {OWNER_USER}", url="https://t.me/mafia_support2")],
    [btn("⚙️ Help", "m_help")],
])


def main_menu(uid):
    return MENU if uid == OWNER_ID else ADMIN_MENU


# key: (button ka naam, text, sirf owner ke liye?)
HELP = {
    "h_onoff": ("🟢 On / Off", "/on naam\n/off naam\n/on all\n/off all\n(sirf aapke liye)\n\nOwner: /forceoff naam ya all (sabke liye band)", False),
    "h_list": ("📋 List", "/list", False),
    "h_add": ("➕ Add / Remove", "/add naam token\n/remove naam", True),
    "h_msg": ("💬 Messages", "/setmsg naam message\n/setall (list ya .txt file)\n/setmsgall message", False),
    "h_chats": ("📨 Chats", "/addchat naam chat_id\n/rmchat naam chat_id\n/chats naam", False),
    "h_link": ("🔗 My Link", "/link naam", False),
    "h_admins": ("👥 Admins", "/addadmin id\n/rmadmin id\n/admins", True),
}
HELP_MENU = InlineKeyboardMarkup(
    [[btn(v[0], k) for k, v in list(HELP.items())[i:i + 2]] for i in range(0, len(HELP), 2)]
    + [[btn("🔙 Back", "m_back")]])
BACK = InlineKeyboardMarkup([[btn("🔙 Back", "m_help")]])
ADMIN_HELP_MENU = InlineKeyboardMarkup([[btn(HELP["h_msg"][0], "h_msg")], [btn("🔙 Back", "m_back")]])


def help_menu(uid):
    return HELP_MENU if uid == OWNER_ID else ADMIN_HELP_MENU
CONTACT = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Owner", url="https://t.me/mafia_support2")]])
WELCOME = "🤖 Welcome to Panel Bot\n\nChoose an option below:"
HELP_TITLE = "⚙️ Help\n\nChoose an option below:"


@admin_only
async def start_cmd(u, c):
    await u.message.reply_text(WELCOME, reply_markup=main_menu(u.effective_user.id))


@admin_only
async def help_cmd(u, c):
    await u.message.reply_text(HELP_TITLE, reply_markup=help_menu(u.effective_user.id))


async def edit(q, text, markup):
    try:
        await q.edit_message_text(text, reply_markup=markup)
    except Exception:
        pass


async def menu_cb(u, c):
    q = u.callback_query
    uid = q.from_user.id
    await q.answer()
    if not is_admin(uid):
        return
    d = q.data
    if d == "m_back":
        return await edit(q, WELCOME, main_menu(uid))
    if d == "m_help":
        return await edit(q, HELP_TITLE, help_menu(uid))
    if d in HELP:
        if uid != OWNER_ID and d != "h_msg":
            return
        title, text, owner_only_ = HELP[d]
        if owner_only_ and uid != OWNER_ID:
            text = "Ye option sirf owner ke liye hai"
        return await edit(q, f"{title}\n\n{text}", BACK)
    if d == "m_on":
        for n in names():
            set_active(n, uid, True)
        return await q.message.reply_text("🟢 Aapke liye saare bots START")
    if d == "m_off":
        for n in names():
            set_active(n, uid, False)
        return await q.message.reply_text("🔴 Aapke liye saare bots STOP")
    if d == "m_list":
        return await q.message.reply_text(status_for(uid))
    if d == "m_admins":
        t = f"👑 Owner: {OWNER_USER}"
        if uid == OWNER_ID:
            ids = [str(r[0]) for r in db.execute("SELECT id FROM admins")]
            t += "\n\nAdmins:\n" + ("\n".join(ids) or "koi nahi")
        return await q.message.reply_text(t, reply_markup=CONTACT)
    if d == "m_add":
        t = "Naya bot add karne ke liye:\n/add naam token" if uid == OWNER_ID else "Ye option sirf owner ke liye hai"
        await q.message.reply_text(t)


@admin_only
async def on(u, c):
    t = c.args[0] if c.args else ""
    targets = names() if t == "all" else [t] if t in names() else []
    if not targets:
        return await u.message.reply_text("Bot nahi mila")
    for n in targets:
        set_active(n, u.effective_user.id, True)
    await u.message.reply_text(f"START ✅ (sirf aapke liye) {', '.join(targets)}")


@admin_only
async def off(u, c):
    t = c.args[0] if c.args else ""
    targets = names() if t == "all" else [t] if t in names() else []
    if not targets:
        return await u.message.reply_text("Bot nahi mila")
    for n in targets:
        set_active(n, u.effective_user.id, False)
    await u.message.reply_text(f"STOP 🛑 (sirf aapke liye) {', '.join(targets)}")


@admin_only
async def list_cmd(u, c):
    rows = names()
    await u.message.reply_text(status_for(u.effective_user.id))


@owner_only
async def add(u, c):
    if len(c.args) < 2:
        return await u.message.reply_text("Use: /add naam token")
    db.execute("INSERT OR REPLACE INTO bots VALUES(?,?,0)", (c.args[0], c.args[1]))
    db.commit()
    try:
        await u.message.delete()
    except Exception:
        pass
    await c.bot.send_message(OWNER_ID, f"{c.args[0]} add ho gaya. /on {c.args[0]}")


@owner_only
async def remove(u, c):
    n = c.args[0] if c.args else ""
    if n in names():
        force_off(n)
    db.execute("DELETE FROM bots WHERE name=?", (n,))
    db.commit()
    await u.message.reply_text(f"{n} delete")


@owner_only
async def addadmin(u, c):
    try:
        db.execute("INSERT OR IGNORE INTO admins VALUES(?)", (int(c.args[0]),))
        db.commit()
        await u.message.reply_text("Admin add ho gaya ✅")
    except Exception:
        await u.message.reply_text("Use: /addadmin telegram_id")


@owner_only
async def rmadmin(u, c):
    try:
        db.execute("DELETE FROM admins WHERE id=?", (int(c.args[0]),))
        db.commit()
        await u.message.reply_text("Admin hata diya ❌")
    except Exception:
        await u.message.reply_text("Use: /rmadmin telegram_id")


@owner_only
async def admins(u, c):
    ids = [str(r[0]) for r in db.execute("SELECT id FROM admins")]
    await u.message.reply_text("Admins:\n" + ("\n".join(ids) or "koi nahi"))


def bot_token(name):
    (token,) = db.execute("SELECT token FROM bots WHERE name=?", (name,)).fetchone()
    return token


def write_msg(name, text, admin_id):
    with open(f"msg_{bot_token(name).split(':')[0]}_{admin_id}.txt", "w", encoding="utf-8") as f:
        f.write(text.replace("\\n", "\n"))


def read_chats(name):
    d = {}
    try:
        for line in open(f"chats_{bot_token(name).split(':')[0]}.txt").read().splitlines():
            p = line.split()
            if p:
                d[p[0]] = p[1] if len(p) > 1 else str(OWNER_ID)
    except FileNotFoundError:
        pass
    return d


def write_chats(name, d):
    with open(f"chats_{bot_token(name).split(':')[0]}.txt", "w") as f:
        f.write("\n".join(f"{k} {v}" for k, v in d.items()))


@admin_only
async def setmsg(u, c):
    if len(c.args) < 2 or c.args[0] not in names():
        return await u.message.reply_text("Use: /setmsg naam apna message")
    write_msg(c.args[0], u.message.text.split(None, 2)[2], u.effective_user.id)
    await u.message.reply_text(f"{c.args[0]}: aapka message set ✅ (sirf aapke users ko jayega)")


@admin_only
async def addchat(u, c):
    if len(c.args) < 2 or c.args[0] not in names():
        return await u.message.reply_text("Use: /addchat naam chat_id")
    d = read_chats(c.args[0])
    for cid in c.args[1:]:
        d[cid] = str(u.effective_user.id)
    write_chats(c.args[0], d)
    mine = sum(1 for v in d.values() if v == str(u.effective_user.id))
    await u.message.reply_text(f"{c.args[0]}: aapke {mine} chat ho gaye ✅")


@admin_only
async def rmchat(u, c):
    if len(c.args) < 2 or c.args[0] not in names():
        return await u.message.reply_text("Use: /rmchat naam chat_id")
    uid = u.effective_user.id
    d = read_chats(c.args[0])
    for cid in c.args[1:]:
        if cid in d and (uid == OWNER_ID or d[cid] == str(uid)):
            del d[cid]
    write_chats(c.args[0], d)
    await u.message.reply_text(f"{c.args[0]}: hata diya")


@admin_only
async def chats_cmd(u, c):
    if not c.args or c.args[0] not in names():
        return await u.message.reply_text("Use: /chats naam")
    uid = u.effective_user.id
    d = read_chats(c.args[0])
    if uid == OWNER_ID:
        lines = [f"{k} (admin {v})" for k, v in d.items()]
    else:
        lines = [k for k, v in d.items() if v == str(uid)]
    await u.message.reply_text("\n".join(lines) or "Koi chat nahi")


@admin_only
async def link(u, c):
    if not c.args or c.args[0] not in names():
        return await u.message.reply_text("Use: /link naam")
    try:
        async with Bot(bot_token(c.args[0])) as b:
            me = await b.get_me()
    except Exception:
        return await u.message.reply_text("Bot ka token galat lag raha hai")
    await u.message.reply_text(
        f"🔗 Aapka link:\nhttps://t.me/{me.username}?start={u.effective_user.id}\n\n"
        "Is link se jo bhi bot start karega, use sirf aapka message milega.")


def apply_list(body, admin_id):
    known, ok, bad = set(names()), [], []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        name, sep, text = line.partition(":")
        name, text = name.strip(), text.strip()
        if sep and name in known and text:
            write_msg(name, text, admin_id)
            ok.append(name)
        else:
            bad.append(name or line[:15])
    r = f"✅ {len(ok)} bot ka message set ho gaya"
    if bad:
        r += f"\n❌ Nahi hue ({len(bad)}): " + ", ".join(bad[:30])
    return r


@admin_only
async def setall(u, c):
    parts = u.message.text.split(None, 1)
    if len(parts) < 2:
        return await u.message.reply_text(
            "Use:\n/setall\nclient1: pehla message\nclient2: doosra message\n...\n\n"
            "Ya .txt file bhejo (caption: /setall)")
    await u.message.reply_text(apply_list(parts[1], u.effective_user.id))


async def setall_file(u, c):
    if not is_admin(u.effective_user.id):
        return
    f = await u.message.document.get_file()
    body = bytes(await f.download_as_bytearray()).decode("utf-8", errors="ignore")
    await u.message.reply_text(apply_list(body, u.effective_user.id))


@admin_only
async def setmsgall(u, c):
    parts = u.message.text.split(None, 1)
    if len(parts) < 2:
        return await u.message.reply_text("Use: /setmsgall message")
    for n in names():
        write_msg(n, parts[1], u.effective_user.id)
    await u.message.reply_text(f"✅ {len(names())} bots par aapka message set ho gaya")


@owner_only
async def forceoff(u, c):
    t = c.args[0] if c.args else ""
    targets = names() if t == "all" else [t] if t in names() else []
    if not targets:
        return await u.message.reply_text("Use: /forceoff naam (ya all)")
    for n in targets:
        force_off(n)
    await u.message.reply_text(f"⛔ Sabke liye band: {', '.join(targets)}")


async def post_init(app):
    for (n,) in db.execute("SELECT name FROM bots WHERE active=1").fetchall():
        start_bot(n)


app = Application.builder().token(PANEL_TOKEN).post_init(post_init).build()
for cmd, fn in [("start", start_cmd), ("help", help_cmd), ("on", on), ("off", off), ("list", list_cmd),
                ("add", add), ("remove", remove), ("addadmin", addadmin),
                ("rmadmin", rmadmin), ("admins", admins), ("setmsg", setmsg), ("setall", setall), ("setmsgall", setmsgall),
                ("link", link), ("forceoff", forceoff), ("addchat", addchat), ("rmchat", rmchat), ("chats", chats_cmd)]:
    app.add_handler(CommandHandler(cmd, fn))
app.add_handler(MessageHandler(filters.Document.ALL & filters.CaptionRegex(r"^/setall"), setall_file))
app.add_handler(CallbackQueryHandler(menu_cb))
app.run_polling()

