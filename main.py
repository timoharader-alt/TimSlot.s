import hmac, hashlib, json, random, time, sqlite3, os
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from datetime import date
from pathlib import Path
from typing import Union, List

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BASE_DIR = Path(__file__).resolve().parent
# На Render подключите Persistent Disk и задайте DB_PATH=/data/slot.db, иначе БД стирается при каждом деплое
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "slot.db"))
app = FastAPI()


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ---------- БД ----------
# Колонки users, которые разрешено обновлять через set_user (whitelist)
USER_COLS = {
    "balance", "wheel_time", "wheel_daily", "wheel_day", "free_spins", "xp", "level",
    "referrer_id", "ref_count", "is_spinning", "fs_bet", "last_ad",
    "fish_caught", "total_wilds", "usd", "eur", "aed",
    "last_collect", "daily_streak", "last_daily", "avatar",
}


def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        uid INTEGER PRIMARY KEY, balance INTEGER DEFAULT 5000,
        wheel_time INTEGER DEFAULT 0, wheel_daily INTEGER DEFAULT 0, wheel_day INTEGER DEFAULT 0,
        free_spins INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        referrer_id INTEGER DEFAULT 0, ref_count INTEGER DEFAULT 0,
        is_spinning INTEGER DEFAULT 0, fs_bet INTEGER DEFAULT 0, last_ad INTEGER DEFAULT 0,
        fish_caught INTEGER DEFAULT 0, total_wilds INTEGER DEFAULT 0,
        usd INTEGER DEFAULT 0, eur INTEGER DEFAULT 0, aed INTEGER DEFAULT 0,
        last_collect INTEGER DEFAULT 0, daily_streak INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0,
        avatar TEXT DEFAULT '👤'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS roulette_bets(uid INTEGER, bet_type TEXT, bet_value TEXT, amount INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS roulette_history(uid INTEGER, amount INTEGER, timestamp INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, item_id TEXT, buy_price INTEGER, buy_time INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tournament(uid INTEGER PRIMARY KEY, score INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS quests(uid INTEGER PRIMARY KEY, spins_count INTEGER DEFAULT 0, win_sum INTEGER DEFAULT 0, last_reset INTEGER DEFAULT 0, claimed TEXT DEFAULT '')""")
    # мягкая миграция для уже существующих БД
    try:
        c.execute("ALTER TABLE quests ADD COLUMN claimed TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS clans(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, owner_id INTEGER, total_score INTEGER DEFAULT 0, desc TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS clan_members(uid INTEGER PRIMARY KEY, clan_id INTEGER, role TEXT DEFAULT 'member')""")
    return c


# ---------- Каталоги ----------
ASSETS_CATALOG = {
    "car_lada": {"name": "Лада Приора", "price": 500000, "emoji": "🚗", "income": 0},
    "car_porsche": {"name": "Porsche 911", "price": 5000000, "emoji": "🏎️", "income": 0},
    "car_lambo": {"name": "Lamborghini", "price": 15000000, "emoji": "🚀", "income": 0},
    "house_flat": {"name": "Квартира в Москве", "price": 10000000, "emoji": "🏢", "income": 0},
    "house_villa": {"name": "Вилла в Дубае", "price": 50000000, "emoji": "🏙️", "income": 0},
    "business_cafe": {"name": "Кофейня", "price": 25000000, "emoji": "☕", "income": 500000},
    "business_it": {"name": "IT-Компания", "price": 100000000, "emoji": "💻", "income": 2500000},
}

CURRENCY_RATES = {
    "usd": {"buy": 95, "sell": 85},
    "eur": {"buy": 105, "sell": 95},
    "aed": {"buy": 26, "sell": 22},
}

AVATARS_CATALOG = {
    "dog": {"emoji": "🐶", "price": 100000},
    "wolf": {"emoji": "🐺", "price": 500000},
    "lion": {"emoji": "🦁", "price": 1000000},
    "diamond": {"emoji": "💎", "price": 5000000},
    "crown": {"emoji": "👑", "price": 10000000},
    "rocket": {"emoji": "🚀", "price": 20000000},
    "alien": {"emoji": "👽", "price": 50000000},
}

GAMES = {
    "fruits": {
        "cols": 3, "rows": 1, "min_bet": 10,
        "symbols": [
            {"id": 0, "pay": [0, 10, 30]},
            {"id": 1, "pay": [0, 15, 50]},
            {"id": 2, "pay": [0, 20, 100]},
            {"id": 3, "pay": [0, 50, 200]},
            {"id": 4, "pay": [0, 100, 500]},
            {"id": 5, "pay": [0, 200, 1000]},
        ],
        "scatter": None,
    },
    "fishing": {
        "cols": 5, "rows": 3, "min_bet": 10,
        "symbols": [
            {"id": 0, "pay": [0, 5, 10, 25, 100]},
            {"id": 1, "pay": [0, 5, 10, 25, 100]},
            {"id": 2, "pay": [0, 5, 10, 25, 100]},
            {"id": 3, "pay": [0, 5, 10, 25, 100]},
            {"id": 4, "pay": [0, 5, 10, 25, 100]},
            {"id": 5, "pay": [0, 10, 20, 50, 200]},
            {"id": 6, "pay": [0, 20, 100, 500, 500]},
            {"id": 7, "pay": [0, 20, 100, 500, 500]},
            {"id": 8, "pay": [0, 30, 150, 1000, 1000]},
            {"id": 9, "pay": [5, 50, 200, 2000, 2000]},
        ],
        "scatter": 10,
        "wild": 11,
        "fish_cash": [12, 13, 14, 15],
    },
}

LINES = {
    "fruits": [[0, 0, 0]],
    "fishing": [
        [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [2, 2, 2, 2, 2],
        [0, 1, 2, 1, 0], [2, 1, 0, 1, 2], [0, 0, 1, 2, 2],
        [2, 2, 1, 0, 0], [0, 1, 2, 2, 2], [2, 1, 0, 0, 0],
        [0, 0, 1, 0, 0],
    ],
}


# ---------- Пользователи ----------
def get_user(uid):
    c = db()
    row = c.execute(
        "SELECT balance, wheel_time, wheel_daily, wheel_day, free_spins, xp, level, "
        "referrer_id, ref_count, fs_bet, last_ad, is_spinning, fish_caught, total_wilds, "
        "usd, eur, aed, last_collect, daily_streak, last_daily, avatar "
        "FROM users WHERE uid=?",
        (uid,),
    ).fetchone()
    if not row:
        c.execute("INSERT INTO users(uid, balance) VALUES(?, 5000)", (uid,))
        c.commit()
        row = (5000, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '👤')
    c.close()
    return {
        "balance": row[0], "wheel_time": row[1], "wheel_daily": row[2], "wheel_day": row[3],
        "free_spins": row[4], "xp": row[5], "level": row[6], "referrer_id": row[7],
        "ref_count": row[8], "fs_bet": row[9], "last_ad": row[10], "is_spinning": row[11],
        "fish_caught": row[12], "total_wilds": row[13], "usd": row[14], "eur": row[15],
        "aed": row[16], "last_collect": row[17], "daily_streak": row[18],
        "last_daily": row[19], "avatar": row[20],
    }


def set_user(uid, **kw):
    c = db()
    for k, v in kw.items():
        if k not in USER_COLS:
            raise ValueError(f"unknown user column: {k}")
        c.execute(f"UPDATE users SET {k}=? WHERE uid=?", (v, uid))
    c.commit()
    c.close()


# ---------- Подпись initData ----------
def verify(init_data: str) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN не задан")
    try:
        p = dict(parse_qsl(init_data, strict_parsing=True))
    except Exception:
        raise HTTPException(400, "bad init_data")
    h = p.pop("hash", None)
    if not h:
        raise HTTPException(400, "no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), h):
        raise HTTPException(401, "bad signature")
    return json.loads(p["user"])


# ---------- Генерация сетки и подсчёт выигрыша ----------
def generate_grid(game_key, is_bonus=False, current_wilds=0, is_first_fs=False):
    g = GAMES[game_key]
    cols, rows = g["cols"], g["rows"]
    grid = [[None] * rows for _ in range(cols)]
    fish_prices = {}

    if game_key == "fishing":
        wild_chance = 0.0
        if is_bonus:
            if is_first_fs:
                wild_chance = 0.0
            else:
                if current_wilds < 3:
                    wild_chance = 0.05
                elif current_wilds < 6:
                    wild_chance = 0.04
                elif current_wilds < 9:
                    wild_chance = 0.03
                elif current_wilds < 12:
                    wild_chance = 0.02
                else:
                    wild_chance = 0.01
        else:
            wild_chance = 0.07

        fish_thr = 0.20 if is_bonus else 0.05
        for c in range(cols):
            for r in range(rows):
                rand = random.random()
                if rand < 0.01:
                    grid[c][r] = g["scatter"]
                elif rand < fish_thr:
                    grid[c][r] = random.choice(g["fish_cash"])
                    fish_prices[(c, r)] = random.choice([2, 5, 10, 15, 20, 25, 50, 200])
                elif rand < (fish_thr + wild_chance):
                    grid[c][r] = g["wild"]
                else:
                    grid[c][r] = random.choice(range(10))
        return grid, fish_prices

    weights = [70, 60, 50, 40, 20, 5]
    pool = [s["id"] for s in g["symbols"] for _ in range(weights[s["id"]] if s["id"] < len(weights) else 1)]
    for ci in range(cols):
        col = []
        for _ in range(rows):
            if g["scatter"] is not None and random.random() < 0.02:
                col.append(g["scatter"])
            else:
                col.append(random.choice(pool))
        grid[ci] = col
    return grid, fish_prices


def check_win(grid, game_key, bet, fish_prices, fish_caught=0, total_wilds=0):
    g = GAMES[game_key]
    lines = LINES[game_key]
    total_win = 0
    win_lines = []
    scatters = 0
    wilds_count = 0
    fish_data = []

    if g.get("scatter") is not None:
        for col in grid:
            for sym in col:
                if sym == g["scatter"]:
                    scatters += 1

    if game_key == "fishing":
        wild_coords = [(c, r) for c in range(len(grid)) for r in range(len(grid[c])) if grid[c][r] == g["wild"]]
        wilds_count = len(wild_coords)
        if wilds_count >= 1:
            mult = 1
            if total_wilds >= 12:
                mult = 10
            elif total_wilds >= 8:
                mult = 5
            elif total_wilds >= 4:
                mult = 2
            for c in range(len(grid)):
                for r in range(len(grid[c])):
                    if grid[c][r] in g["fish_cash"]:
                        price_mult = fish_prices.get((c, r), 2)
                        val = price_mult * bet
                        total_win += val * mult
                        fish_data.append({"col": c, "row": r, "val": val, "mult": mult})

    for line_idx, line in enumerate(lines):
        first_sym = grid[0][line[0]]
        if first_sym is None or first_sym >= 10:
            continue
        count = 1
        for col in range(1, len(grid)):
            sym = grid[col][line[col]]
            if sym == first_sym or (game_key == "fishing" and sym == g["wild"]):
                count += 1
            elif first_sym == g.get("wild") and game_key == "fishing":
                first_sym = sym
                count += 1
            else:
                break

        min_match = 2
        if count >= min_match:
            if game_key == "fishing":
                sym_data = g["symbols"][first_sym] if first_sym < 10 else g["symbols"][0]
                idx = count - 2
                mult = sym_data["pay"][idx] if idx < len(sym_data["pay"]) else sym_data["pay"][-1]
            else:
                sym_data = next(s for s in g["symbols"] if s["id"] == first_sym)
                idx = count - min_match
                mult = sym_data["pay"][idx] if idx < len(sym_data["pay"]) else sym_data["pay"][-1]

            if mult > 0:
                payout = bet * mult
                total_win += payout
                win_lines.append({"line": line_idx, "count": count, "win": payout})
    return total_win, win_lines, scatters, fish_data, wilds_count
    # ---------- Модели запросов ----------
class Req(BaseModel):
    init_data: str


class RefReq(BaseModel):
    init_data: str
    referrer_id: int


class SpinReq(BaseModel):
    init_data: str
    bet: int
    game: str
    bonus_buy: bool = False
    free_spins: int = 0


class RoulBet(BaseModel):
    type: str
    value: Union[int, str]
    amount: int


class RoulBetReq(BaseModel):
    init_data: str
    bets: List[RoulBet]


class BuyAssetReq(BaseModel):
    init_data: str
    item_id: str


class ExchangeReq(BaseModel):
    init_data: str
    currency: str
    amount: int
    action: str


class BuyAvatarReq(BaseModel):
    init_data: str
    avatar_id: str


class ClaimQuestReq(BaseModel):
    init_data: str
    quest_id: str


class CreateClanReq(BaseModel):
    init_data: str
    name: str


class JoinClanReq(BaseModel):
    init_data: str
    clan_id: int


# ---------- Эндпоинты ----------
@app.post("/state")
def state(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    today = date.today().toordinal()
    if d["wheel_day"] != today:
        set_user(uid, wheel_daily=0, wheel_day=today)
        d["wheel_daily"] = 0
    if d["is_spinning"] == 1:
        set_user(uid, is_spinning=0)
        d["is_spinning"] = 0
    can_wheel = (d["wheel_daily"] < 5) and (now >= d["wheel_time"])
    time_left = max(0, d["wheel_time"] - now)
    return {
        "balance": int(d["balance"]),
        "wheel_ready": can_wheel,
        "wheel_time_left": time_left,
        "wheel_daily": d["wheel_daily"],
        "ad_ready": now - d["last_ad"] > 60,
        "ad_allowed": d["balance"] < 5000,
        "free_spins": d["free_spins"],
        "level": d["level"],
        "xp": d["xp"],
        "next_level_xp": d["level"] * 15000,
        "ref_count": d["ref_count"],
        "fish_caught": d["fish_caught"],
        "total_wilds": d["total_wilds"],
        "usd": d["usd"],
        "eur": d["eur"],
        "aed": d["aed"],
        "daily_streak": d["daily_streak"],
        "last_daily": d["last_daily"],
        "last_collect": d["last_collect"],
        "avatar": d["avatar"],
    }


@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    if d["is_spinning"] == 1:
        set_user(uid, is_spinning=0)
        d["is_spinning"] = 0
    if r.game not in GAMES:
        raise HTTPException(400, "Неизвестная игра")
    if r.bonus_buy and r.game != "fishing":
        raise HTTPException(400, "Покупка бонуса недоступна в этой игре")
    game_conf = GAMES[r.game]
    is_fs = d["free_spins"] > 0

    if not r.free_spins and not r.bonus_buy and d["free_spins"] > 0:
        set_user(uid, free_spins=0, fish_caught=0, total_wilds=0)
        d["free_spins"] = 0
        d["fish_caught"] = 0
        d["total_wilds"] = 0
        is_fs = False

    actual_bet = d["fs_bet"] if is_fs else (r.bet * 150 if r.bonus_buy else r.bet)
    cost = 0 if is_fs else actual_bet
    if not is_fs and r.bet < game_conf["min_bet"]:
        raise HTTPException(400, f"Мин. ставка {game_conf['min_bet']}")
    if not is_fs and r.bet > 5000:
        raise HTTPException(400, "Максимальная ставка — 5000")
    if d["balance"] < cost:
        raise HTTPException(400, "Недостаточно фишек")
    set_user(uid, is_spinning=1)
    bal = d["balance"] - cost

    is_first_fs = is_fs and d["free_spins"] in [10, 15, 20]
    grid, fish_prices = generate_grid(r.game, is_fs or r.bonus_buy, d["total_wilds"], is_first_fs)
    scatters = 0

    if r.bonus_buy:
        for c in range(len(grid)):
            for row in range(len(grid[c])):
                if grid[c][row] == game_conf.get("scatter"):
                    grid[c][row] = 0
        grid[1][0] = game_conf["scatter"]
        grid[3][1] = game_conf["scatter"]
        grid[2][2] = game_conf["scatter"]
        scatters = 3
        if r.game == "fishing":
            grid[2][1] = game_conf["wild"]
            grid[1][1] = game_conf["fish_cash"][0]
            grid[3][1] = game_conf["fish_cash"][1]
            grid[2][0] = game_conf["fish_cash"][2]
            fish_prices[(1, 1)] = 10
            fish_prices[(3, 1)] = 20
            fish_prices[(2, 0)] = 5
    else:
        if not is_fs and game_conf.get("scatter") is not None:
            for c in grid:
                for sym in c:
                    if sym == game_conf["scatter"]:
                        scatters += 1
        elif is_fs:
            for c in range(len(grid)):
                for row in range(len(grid[c])):
                    if grid[c][row] == game_conf.get("scatter"):
                        grid[c][row] = 0
            if d["free_spins"] == 10 and r.game == "fishing" and not is_first_fs:
                grid[2][1] = game_conf["wild"]
                grid[1][1] = game_conf["fish_cash"][0]
                grid[3][1] = game_conf["fish_cash"][1]
                fish_prices[(1, 1)] = 10
                fish_prices[(3, 1)] = 20

    win_amount, win_lines, scatters_nat, fish_data, wilds_count = check_win(
        grid, r.game, actual_bet, fish_prices, d["fish_caught"], d["total_wilds"]
    )
    if not r.bonus_buy and not is_fs:
        scatters = scatters_nat

    new_free_spins = d["free_spins"]
    new_fish_caught = d["fish_caught"]
    new_fs_bet = d["fs_bet"]
    new_total_wilds = d["total_wilds"]

    if is_fs:
        new_free_spins -= 1
        if wilds_count > 0:
            old_wilds = new_total_wilds
            new_total_wilds += wilds_count
            if (new_total_wilds // 4) > (old_wilds // 4):
                new_free_spins += 10
                if new_total_wilds > 12:
                    new_total_wilds = 12
        if new_free_spins <= 0:
            new_fs_bet = 0
            new_fish_caught = 0
            new_total_wilds = 0
    elif scatters >= 3:
        if scatters == 3:
            new_free_spins = 10
        elif scatters == 4:
            new_free_spins = 15
        elif scatters >= 5:
            new_free_spins = 20
        new_fish_caught = 0
        new_total_wilds = 0
        new_fs_bet = r.bet

    bal += win_amount
    new_xp = d["xp"] + win_amount
    new_level = d["level"]
    next_level_xp = new_level * 15000
    if new_xp >= next_level_xp:
        new_level += 1
        bal += 5000
        new_xp -= next_level_xp
    set_user(
        uid, balance=bal, free_spins=new_free_spins, fs_bet=new_fs_bet,
        xp=new_xp, level=new_level, is_spinning=0,
        fish_caught=new_fish_caught, total_wilds=new_total_wilds,
    )

    c_q = db()
    now_time = int(time.time())
    row_q = c_q.execute("SELECT spins_count, win_sum, last_reset FROM quests WHERE uid=?", (uid,)).fetchone()
    if not row_q:
        c_q.execute(
            "INSERT INTO quests(uid, spins_count, win_sum, last_reset) VALUES(?, 1, ?, ?)",
            (uid, win_amount, now_time),
        )
    else:
        if now_time - row_q[2] > 86400:
            c_q.execute(
                "UPDATE quests SET spins_count=1, win_sum=?, last_reset=? WHERE uid=?",
                (win_amount, now_time, uid),
            )
        else:
            c_q.execute(
                "UPDATE quests SET spins_count=spins_count+1, win_sum=win_sum+? WHERE uid=?",
                (win_amount, uid),
            )
    c_q.commit()
    c_q.close()

    c_t = db()
    if win_amount > 0:
        c_t.execute(
            "INSERT INTO tournament(uid, score) VALUES(?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET score = score + ?",
            (uid, win_amount, win_amount),
        )
    c_t.commit()
    c_t.close()

    c_clan = db()
    member = c_clan.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if member and win_amount > 0:
        c_clan.execute("UPDATE clans SET total_score = total_score + ? WHERE id=?", (win_amount, member[0]))
        c_clan.commit()
    c_clan.close()

    ui_mult = 1
    if new_total_wilds >= 12:
        ui_mult = 10
    elif new_total_wilds >= 8:
        ui_mult = 5
    elif new_total_wilds >= 4:
        ui_mult = 2

    return {
        "grid": grid, "win": win_amount, "balance": bal, "lines": win_lines,
        "scatters": scatters, "bonus_mult": ui_mult, "fish_data": fish_data,
        "is_free_spin": is_fs, "free_spins_left": new_free_spins,
        "fish_caught": new_fish_caught, "level": new_level, "xp": new_xp,
        "wilds_count": wilds_count, "total_wilds": new_total_wilds,
    }


@app.post("/reset_fs")
def reset_fs(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    set_user(uid, free_spins=0, fs_bet=0, fish_caught=0, total_wilds=0)
    return {"status": "ok"}


@app.post("/roulette/bet")
def roul_bet(r: RoulBetReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    if not r.bets or len(r.bets) > 100:
        raise HTTPException(400, "Неверные ставки")
    for b in r.bets:
        if b.amount <= 0:
            raise HTTPException(400, "Ставка должна быть > 0")
        if b.type == 'number':
            try:
                if not 0 <= int(b.value) <= 36:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(400, "Неверное число")
        elif (b.type, str(b.value)) not in {
            ('color', 'red'), ('color', 'black'), ('parity', 'even'), ('parity', 'odd'),
            ('half', 'low'), ('half', 'high'),
        }:
            raise HTTPException(400, "Неверная ставка")
    total_bet = sum(b.amount for b in r.bets)
    if total_bet <= 0:
        raise HTTPException(400, "Ставка не может быть 0")
    if total_bet > 5000:
        raise HTTPException(400, "Максимальная общая ставка — 5000")

    c = db()
    one_hour_ago = now - 3600
    c.execute("DELETE FROM roulette_history WHERE timestamp < ?", (now - 86400,))
    total_last_hour = c.execute(
        "SELECT SUM(amount) FROM roulette_history WHERE uid=? AND timestamp > ?",
        (uid, one_hour_ago),
    ).fetchone()[0] or 0
    if total_last_hour + total_bet > 100000:
        c.close()
        raise HTTPException(400, f"Лимит 100000 в час. Вы поставили: {total_last_hour}")
    if d["balance"] < total_bet:
        c.close()
        raise HTTPException(400, "Мало фишек")

    new_balance = int(d["balance"] - total_bet)
    set_user(uid, balance=new_balance)
    c.execute("INSERT INTO roulette_history(uid, amount, timestamp) VALUES(?,?,?)", (uid, total_bet, now))
    c.execute("DELETE FROM roulette_bets WHERE uid=?", (uid,))
    for b in r.bets:
        c.execute(
            "INSERT INTO roulette_bets(uid, bet_type, bet_value, amount) VALUES (?,?,?,?)",
            (uid, b.type, str(b.value), b.amount),
        )
    c.commit()
    c.close()
    return {"status": "ok", "balance": new_balance}


@app.post("/roulette/spin")
def roul_spin(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    c = db()
    c.execute("BEGIN IMMEDIATE")
    bets = c.execute("SELECT bet_type, bet_value, amount FROM roulette_bets WHERE uid=?", (uid,)).fetchall()
    if not bets:
        c.close()
        raise HTTPException(400, "Нет ставок")
    c.execute("DELETE FROM roulette_bets WHERE uid=?", (uid,))
    c.commit()
    c.close()
    win_num = int(random.randint(0, 36))
    is_red = win_num in [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    is_black = win_num != 0 and not is_red
    total_win = 0
    for b_type, b_val, amount in bets:
        amount = int(amount)
        if b_type == 'number':
            if int(b_val) == win_num:
                total_win += amount * (10 if win_num == 0 else 36)
        elif b_type == 'color':
            if b_val == 'red' and is_red:
                total_win += amount * 2
            if b_val == 'black' and is_black:
                total_win += amount * 2
        elif b_type == 'parity':
            if b_val == 'even' and win_num != 0 and win_num % 2 == 0:
                total_win += amount * 2
            if b_val == 'odd' and win_num % 2 != 0:
                total_win += amount * 2
        elif b_type == 'half':
            if b_val == 'low' and 1 <= win_num <= 18:
                total_win += amount * 3
            if b_val == 'high' and 19 <= win_num <= 36:
                total_win += amount * 3
    new_balance = int(d["balance"] + total_win)
    set_user(uid, balance=new_balance)
    return {"win_num": win_num, "win_amount": int(total_win), "balance": new_balance}


@app.post("/referral")
def referral(r: RefReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    if uid == r.referrer_id or d["referrer_id"] != 0:
        return {"status": "error"}
    c = db()
    ref_row = c.execute("SELECT uid FROM users WHERE uid=?", (r.referrer_id,)).fetchone()
    if not ref_row:
        c.close()
        return {"status": "error"}
    c.execute("UPDATE users SET referrer_id=?, balance=balance+1000 WHERE uid=?", (r.referrer_id, uid))
    c.execute("UPDATE users SET ref_count=ref_count+1, balance=balance+2000 WHERE uid=?", (r.referrer_id,))
    c.commit()
    c.close()
    return {"status": "success"}


@app.post("/bonus")
def bonus(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    if d["wheel_daily"] >= 5:
        raise HTTPException(400, "Лимит 5 круток")
    if now < d["wheel_time"]:
        raise HTTPException(400, "Кулдаун 1 час")
    rnd = random.random() * 100
    if rnd < 1:
        amount = 1000
    elif rnd < 4:
        amount = 500
    elif rnd < 12:
        amount = 250
    elif rnd < 32:
        amount = 100
    elif rnd < 62:
        amount = 50
    elif rnd < 87:
        amount = 20
    else:
        amount = 0
    set_user(uid, balance=d["balance"] + amount, wheel_time=now + 3600, wheel_daily=d["wheel_daily"] + 1)
    return {"amount": amount, "balance": d["balance"] + amount}


@app.post("/ad")
def ad(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    if now - d["last_ad"] < 60:
        raise HTTPException(400, "Подожди минуту")
    if d["balance"] >= 5000:
        raise HTTPException(400, "реклама доступна только при балансе < 5000")
    amount = random.choice([100, 200, 300, 500])
    set_user(uid, balance=d["balance"] + amount, last_ad=now)
    return {"amount": amount, "balance": d["balance"] + amount}
    @app.post("/get_assets")
def get_assets(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    rows = c.execute("SELECT id, item_id, buy_price FROM assets WHERE uid=?", (uid,)).fetchall()
    c.close()
    assets = []
    total_value = 0
    for r_id, item_id, price in rows:
        item = ASSETS_CATALOG.get(item_id, {"name": "Неизвестно", "price": 0, "emoji": "❓"})
        assets.append({"id": r_id, "item_id": item_id, "name": item["name"], "emoji": item["emoji"], "price": price})
        total_value += price
    return {"assets": assets, "total_value": total_value}


@app.post("/buy_asset")
def buy_asset(r: BuyAssetReq):
    u = verify(r.init_data)
    uid = u["id"]
    item = ASSETS_CATALOG.get(r.item_id)
    if not item:
        raise HTTPException(400, "Товар не найден")
    d = get_user(uid)
    if d["balance"] < item["price"]:
        raise HTTPException(400, "Недостаточно фишек")
    new_bal = d["balance"] - item["price"]
    set_user(uid, balance=new_bal)
    c = db()
    c.execute(
        "INSERT INTO assets(uid, item_id, buy_price, buy_time) VALUES(?,?,?,?)",
        (uid, r.item_id, item["price"], int(time.time())),
    )
    c.commit()
    c.close()
    return {"status": "ok", "balance": new_bal, "message": f"Вы купили {item['name']}!"}


@app.post("/sell_asset")
def sell_asset(r: BuyAssetReq):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    row = c.execute("SELECT item_id, buy_price FROM assets WHERE id=? AND uid=?", (int(r.item_id), uid)).fetchone()
    if not row:
        c.close()
        raise HTTPException(400, "Имущество не найдено")
    item_id, buy_price = row
    refund = int(buy_price * 0.7)
    c.execute("DELETE FROM assets WHERE id=? AND uid=?", (int(r.item_id), uid))
    c.commit()
    c.close()
    d = get_user(uid)
    new_bal = d["balance"] + refund
    set_user(uid, balance=new_bal)
    return {"status": "ok", "balance": new_bal, "message": f"Вы продали за {refund} фишек"}


@app.post("/collect_income")
def collect_income(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    last_collect = d.get("last_collect", 0)
    # первый сбор: фиксируем точку отсчёта без начисления
    if last_collect == 0:
        set_user(uid, last_collect=now)
        raise HTTPException(400, "Доход начнёт копиться с этого момента")
    time_passed = min(now - last_collect, 18000)
    if time_passed < 3600:
        raise HTTPException(400, f"Ждать: {((3600 - time_passed) // 60)} мин.")
    c = db()
    rows = c.execute("SELECT item_id FROM assets WHERE uid=?", (uid,)).fetchall()
    c.close()
    total_income_per_hour = sum(ASSETS_CATALOG.get(item_id, {}).get("income", 0) for (item_id,) in rows)
    if total_income_per_hour == 0:
        raise HTTPException(400, "Нет бизнеса")
    hours = int(time_passed // 3600)
    total_income = total_income_per_hour * hours
    new_bal = d["balance"] + total_income
    set_user(uid, balance=new_bal, last_collect=now)
    return {"status": "ok", "amount": total_income, "hours": hours, "balance": new_bal}


@app.post("/exchange")
def exchange(r: ExchangeReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    if r.currency not in CURRENCY_RATES:
        raise HTTPException(400, "Валюта не поддерживается")
    if r.amount <= 0:
        raise HTTPException(400, "Сумма > 0")
    rate = CURRENCY_RATES[r.currency]
    if r.action == 'buy':
        cost = r.amount * rate["buy"]
        if d["balance"] < cost:
            raise HTTPException(400, "Мало фишек")
        new_bal = d["balance"] - cost
        new_wallet = d.get(r.currency, 0) + r.amount
        set_user(uid, **{"balance": new_bal, r.currency: new_wallet})
        return {"status": "ok", "balance": new_bal, "wallet": new_wallet}
    elif r.action == 'sell':
        current_wallet = d.get(r.currency, 0)
        if current_wallet < r.amount:
            raise HTTPException(400, "Мало валюты")
        gain = r.amount * rate["sell"]
        new_bal = d["balance"] + gain
        new_wallet = current_wallet - r.amount
        set_user(uid, **{"balance": new_bal, r.currency: new_wallet})
        return {"status": "ok", "balance": new_bal, "wallet": new_wallet}
    raise HTTPException(400, "Неверное действие")


@app.post("/buy_avatar")
def buy_avatar(r: BuyAvatarReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    item = AVATARS_CATALOG.get(r.avatar_id)
    if not item:
        raise HTTPException(400, "Аватар не найден")
    if d["balance"] < item["price"]:
        raise HTTPException(400, "Мало фишек")
    new_bal = d["balance"] - item["price"]
    set_user(uid, balance=new_bal, avatar=item["emoji"])
    return {"status": "ok", "balance": new_bal, "avatar": item["emoji"]}


@app.post("/open_case")
def open_case(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    COST = 50000
    if d["balance"] < COST:
        raise HTTPException(400, f"Нужно {COST} фишек")
    new_bal = d["balance"] - COST
    rnd = random.random() * 100
    prize_type = ""
    prize_value = 0
    prize_text = ""
    if rnd < 1:
        prize_type = "car_lambo"
        prize_text = "🚀 Lamborghini!"
        c = db()
        c.execute(
            "INSERT INTO assets(uid, item_id, buy_price, buy_time) VALUES(?,?,?,?)",
            (uid, "car_lambo", 15000000, now),
        )
        c.commit()
        c.close()
    elif rnd < 5:
        prize_type = "usd"
        prize_value = 10
        prize_text = "💵 10 USD"
        d["usd"] += 10
    elif rnd < 15:
        prize_type = "chips"
        prize_value = 500000
        prize_text = "💰 500 000 фишек"
        new_bal += prize_value
    elif rnd < 40:
        prize_type = "chips"
        prize_value = 100000
        prize_text = "💰 100 000 фишек"
        new_bal += prize_value
    elif rnd < 70:
        prize_type = "chips"
        prize_value = 50000
        prize_text = "💰 50 000 фишек"
        new_bal += prize_value
    else:
        prize_type = "empty"
        prize_text = "😢 Пусто"
    set_user(uid, balance=new_bal, usd=d["usd"])
    return {
        "status": "ok", "prize_type": prize_type, "prize_value": prize_value,
        "prize_text": prize_text, "balance": new_bal,
    }


@app.post("/get_quests")
def get_quests(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    row = c.execute("SELECT spins_count, win_sum, last_reset FROM quests WHERE uid=?", (uid,)).fetchone()
    now = int(time.time())
    if not row or (now - row[2] > 86400):
        if not row:
            c.execute(
                "INSERT INTO quests(uid, spins_count, win_sum, last_reset) VALUES(?, 0, 0, ?)",
                (uid, now),
            )
        else:
            c.execute("UPDATE quests SET spins_count=0, win_sum=0, last_reset=? WHERE uid=?", (now, uid))
        c.commit()
        spins, wins = 0, 0
    else:
        spins, wins = row[0], row[1]
    c.close()
    quests_list = [
        {"id": "spins_10", "text": "Сделай 10 спинов", "target": 10, "progress": spins, "reward": 5000},
        {"id": "spins_50", "text": "Сделай 50 спинов", "target": 50, "progress": spins, "reward": 25000},
        {"id": "win_100k", "text": "Выиграй 100 000 фишек", "target": 100000, "progress": wins, "reward": 50000},
        {"id": "win_1m", "text": "Выиграй 1 000 000 фишек", "target": 1000000, "progress": wins, "reward": 500000},
    ]
    return {"quests": quests_list}


@app.post("/claim_quest")
def claim_quest(r: ClaimQuestReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    c = db()
    row = c.execute("SELECT spins_count, win_sum, claimed FROM quests WHERE uid=?", (uid,)).fetchone()
    if not row:
        c.close()
        raise HTTPException(400, "Ошибка")
    spins, wins, claimed_raw = row[0], row[1], (row[2] or "")
    c.close()
    rewards = {"spins_10": 5000, "spins_50": 25000, "win_100k": 50000, "win_1m": 500000}
    targets = {"spins_10": 10, "spins_50": 50, "win_100k": 100000, "win_1m": 1000000}
    if r.quest_id not in rewards:
        raise HTTPException(400, "Неизвестный")
    # защита от повторного клейма
    claimed = set(x for x in claimed_raw.split(",") if x)
    if r.quest_id in claimed:
        raise HTTPException(400, "Уже получено")
    if r.quest_id.startswith("spins") and spins < targets[r.quest_id]:
        raise HTTPException(400, "Не выполнен")
    if r.quest_id.startswith("win") and wins < targets[r.quest_id]:
        raise HTTPException(400, "Не выполнен")
    reward = rewards[r.quest_id]
    new_bal = d["balance"] + reward
    set_user(uid, balance=new_bal)
    claimed.add(r.quest_id)
    c = db()
    c.execute("UPDATE quests SET claimed=? WHERE uid=?", (",".join(claimed), uid))
    c.commit()
    c.close()
    return {"status": "ok", "balance": new_bal}


@app.post("/daily")
def daily(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    now = int(time.time())
    today = date.today().toordinal()
    last_daily = d["last_daily"] or 0
    last_day = date.fromtimestamp(last_daily).toordinal() if last_daily else 0
    # streak продолжается, если зашли вчера/сегодня; иначе сбрасывается
    if last_daily and (today - last_day == 1 or (today == last_day and now - last_daily < 86400)):
        streak = d["daily_streak"] + 1 if today != last_day else d["daily_streak"]
    else:
        streak = 1
    if streak > 7:
        streak = 1
    if last_daily and today == last_day and now - last_daily < 86400:
        raise HTTPException(400, "Уже получено сегодня")
    rewards = {1: 1000, 2: 2500, 3: 5000, 4: 10000, 5: 25000, 6: 50000, 7: 100000}
    amount = rewards[streak]
    new_bal = d["balance"] + amount
    new_usd = d["usd"]
    if streak == 7:
        new_usd += 10
    set_user(
        uid, balance=new_bal, usd=new_usd,
        daily_streak=streak, last_daily=now,
    )
    return {"status": "ok", "day": streak, "amount": amount, "balance": new_bal}


@app.post("/create_clan")
def create_clan(r: CreateClanReq):
    u = verify(r.init_data)
    uid = u["id"]
    d = get_user(uid)
    COST = 1000000
    name = r.name.strip()
    if not 3 <= len(name) <= 24:
        raise HTTPException(400, "Название: от 3 до 24 символов")
    r.name = name
    if d["balance"] < COST:
        raise HTTPException(400, "Нужно 1 000 000")
    c = db()
    existing = c.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if existing:
        c.close()
        raise HTTPException(400, "Вы уже в клане")
    try:
        cur = c.execute("INSERT INTO clans(name, owner_id) VALUES(?, ?)", (r.name, uid))
        clan_id = cur.lastrowid
        c.execute("INSERT INTO clan_members(uid, clan_id, role) VALUES(?, ?, 'owner')", (uid, clan_id))
        new_bal = d["balance"] - COST
        c.execute("UPDATE users SET balance=? WHERE uid=?", (new_bal, uid))
        c.commit()
        c.close()
        return {"status": "ok", "balance": new_bal, "message": "Клан создан!"}
    except sqlite3.IntegrityError:
        c.close()
        raise HTTPException(400, "Название занято")


@app.post("/get_clans")
def get_clans(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    my_clan = c.execute("SELECT clan_id, role FROM clan_members WHERE uid=?", (uid,)).fetchone()
    clans = c.execute("SELECT id, name, total_score FROM clans ORDER BY total_score DESC LIMIT 20").fetchall()
    c.close()
    my_data = None
    if my_clan:
        cid, role = my_clan
        c = db()
        row = c.execute("SELECT id, name, total_score FROM clans WHERE id=?", (cid,)).fetchone()
        if row:
            members = c.execute("SELECT COUNT(*) FROM clan_members WHERE clan_id=?", (cid,)).fetchone()[0]
            my_data = {"id": row[0], "name": row[1], "score": row[2], "members": members, "role": role}
        c.close()
    return {"my_clan": my_data, "top_clans": [{"id": r[0], "name": r[1], "score": r[2]} for r in clans]}


@app.post("/join_clan")
def join_clan(r: JoinClanReq):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    existing = c.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if existing:
        c.close()
        raise HTTPException(400, "Вы уже в клане")
    clan = c.execute("SELECT id FROM clans WHERE id=?", (r.clan_id,)).fetchone()
    if not clan:
        c.close()
        raise HTTPException(400, "Клан не найден")
    c.execute("INSERT INTO clan_members(uid, clan_id) VALUES(?, ?)", (uid, r.clan_id))
    c.commit()
    c.close()
    return {"status": "ok"}


@app.post("/leave_clan")
def leave_clan(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    member = c.execute("SELECT clan_id, role FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if not member:
        c.close()
        raise HTTPException(400, "Вы не в клане")
    cid, role = member
    if role == 'owner':
        c.execute("DELETE FROM clans WHERE id=?", (cid,))
    c.execute("DELETE FROM clan_members WHERE uid=?", (uid,))
    c.commit()
    c.close()
    return {"status": "ok"}


@app.post("/tournament")
def get_tournament(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    rows = c.execute(
        "SELECT t.uid, t.score, u.avatar FROM tournament t "
        "JOIN users u ON t.uid = u.uid ORDER BY t.score DESC LIMIT 10"
    ).fetchall()
    my_score_row = c.execute("SELECT score FROM tournament WHERE uid=?", (uid,)).fetchone()
    my_score = my_score_row[0] if my_score_row else 0
    c.close()
    top = [
        {"rank": i + 1, "name": f"{str(r[0])[:3]}***{str(r[0])[-2:]}", "score": r[1], "avatar": r[2] or '👤'}
        for i, r in enumerate(rows)
    ]
    return {"top": top, "my_score": my_score}


@app.post("/rating")
def rating(r: Req):
    u = verify(r.init_data)
    uid = u["id"]
    c = db()
    query = """
    SELECT u.uid, u.balance, u.avatar, COALESCE(SUM(a.buy_price), 0) as assets_value,
           (u.balance + COALESCE(SUM(a.buy_price), 0)) as total_capital
    FROM users u LEFT JOIN assets a ON u.uid = a.uid
    GROUP BY u.uid ORDER BY total_capital DESC LIMIT 10
    """
    rows = c.execute(query).fetchall()
    c.close()
    top = [
        {"rank": i + 1, "name": f"{str(r[0])[:3]}***{str(r[0])[-2:]}", "balance": r[1],
         "assets": r[3], "capital": r[4], "avatar": r[2] or '👤'}
        for i, r in enumerate(rows)
    ]
    return {"top": top}


@app.on_event("startup")
def _startup():
    db().close()  # создаём таблицы сразу при старте


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")
