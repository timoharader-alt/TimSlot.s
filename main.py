import hmac, hashlib, json, random, time, sqlite3, os, threading, re
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})

_db_lock = threading.Lock()
_db_conn = None

ALLOWED_USER_COLUMNS = {
    "balance","wheel_time","wheel_daily","wheel_day","free_spins","xp","level",
    "referrer_id","ref_count","is_spinning","fs_bet","last_ad","fish_caught",
    "total_wilds","usd","eur","aed","last_collect","daily_streak","last_daily",
    "avatar","ref_earnings","vip_expires","last_black_market","energy","pickaxe_lvl",
    "active_skin","active_frame","last_energy_time"
}

def db():
    global _db_conn
    with _db_lock:
        if _db_conn is None:
            _db_conn = sqlite3.connect("slot.db", timeout=30, check_same_thread=False)
            _db_conn.execute("PRAGMA journal_mode=WAL;")
            _db_conn.execute("PRAGMA synchronous=NORMAL;")
            _db_conn.execute("PRAGMA busy_timeout = 30000;")
            conn = _db_conn
            conn.execute("""CREATE TABLE IF NOT EXISTS users(
                uid INTEGER PRIMARY KEY, balance INTEGER DEFAULT 5000, 
                wheel_time INTEGER DEFAULT 0, wheel_daily INTEGER DEFAULT 0, wheel_day INTEGER DEFAULT 0, 
                free_spins INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
                referrer_id INTEGER DEFAULT 0, ref_count INTEGER DEFAULT 0,
                is_spinning INTEGER DEFAULT 0, fs_bet INTEGER DEFAULT 0, last_ad INTEGER DEFAULT 0,
                fish_caught INTEGER DEFAULT 0, total_wilds INTEGER DEFAULT 0,
                usd INTEGER DEFAULT 0, eur INTEGER DEFAULT 0, aed INTEGER DEFAULT 0,
                last_collect INTEGER DEFAULT 0, daily_streak INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0,
                avatar TEXT DEFAULT '👤', ref_earnings INTEGER DEFAULT 0, vip_expires INTEGER DEFAULT 0,
                last_black_market INTEGER DEFAULT 0, energy INTEGER DEFAULT 1000, pickaxe_lvl INTEGER DEFAULT 1,
                active_skin TEXT DEFAULT 'default', active_frame TEXT DEFAULT 'default', last_energy_time INTEGER DEFAULT 0
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS roulette_bets(uid INTEGER, bet_type TEXT, bet_value TEXT, amount INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS roulette_history(uid INTEGER, amount INTEGER, timestamp INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, item_id TEXT, buy_price INTEGER, buy_time INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS tournament(uid INTEGER PRIMARY KEY, score INTEGER DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS quests(uid INTEGER PRIMARY KEY, spins_count INTEGER DEFAULT 0, win_sum INTEGER DEFAULT 0, last_reset INTEGER DEFAULT 0, taps_count INTEGER DEFAULT 0, mine_earned INTEGER DEFAULT 0, pickaxe_upgrades INTEGER DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS claimed_quests(uid INTEGER, quest_id TEXT, day INTEGER, PRIMARY KEY(uid, quest_id, day))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS user_skins(uid INTEGER, skin_id TEXT, PRIMARY KEY(uid, skin_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS auction(id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, asset_id INTEGER, item_id TEXT, price INTEGER, created_at INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS clans(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, owner_id INTEGER, total_score INTEGER DEFAULT 0, desc TEXT DEFAULT '')""")
            conn.execute("""CREATE TABLE IF NOT EXISTS clan_members(uid INTEGER PRIMARY KEY, clan_id INTEGER, role TEXT DEFAULT 'member')""")
            conn.execute("""CREATE TABLE IF NOT EXISTS global_jackpot(id INTEGER PRIMARY KEY, amount INTEGER DEFAULT 0)""")
            conn.execute("""INSERT OR IGNORE INTO global_jackpot(id, amount) VALUES(1, 1000000)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS promocodes(code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS promo_activations(uid INTEGER, code TEXT, PRIMARY KEY(uid, code))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS market_rates(item_id TEXT PRIMARY KEY, current_price INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS crypto(uid INTEGER PRIMARY KEY, tim_balance REAL DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS crypto_market(id INTEGER PRIMARY KEY, price REAL DEFAULT 100, last_update INTEGER DEFAULT 0)""")
            conn.execute("""INSERT OR IGNORE INTO crypto_market(id, price) VALUES(1, 100)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS black_market(id INTEGER PRIMARY KEY AUTOINCREMENT, item_name TEXT, description TEXT, price INTEGER, reward_value INTEGER, risk_chance REAL, expires_at INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS active_events(id INTEGER PRIMARY KEY, event_type TEXT, multiplier REAL, expires_at INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS clan_wars(id INTEGER PRIMARY KEY, clan1_id INTEGER, clan2_id INTEGER, start_time INTEGER, end_time INTEGER, clan1_score INTEGER DEFAULT 0, clan2_score INTEGER DEFAULT 0, status TEXT DEFAULT 'active')""")
            conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, clan_id INTEGER DEFAULT 0, text TEXT, timestamp INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS player_house(uid INTEGER PRIMARY KEY, level INTEGER DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS story_progress(uid INTEGER PRIMARY KEY, chapter INTEGER DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS predictions(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, option_yes TEXT, option_no TEXT, end_time INTEGER, result TEXT DEFAULT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS prediction_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, prediction_id INTEGER, choice TEXT, amount INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS tech_tree(uid INTEGER, node_id TEXT, level INTEGER DEFAULT 1, PRIMARY KEY(uid, node_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS clan_chest(clan_id INTEGER PRIMARY KEY, current_amount INTEGER DEFAULT 0, goal_amount INTEGER DEFAULT 100000000)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS clan_chest_history(id INTEGER PRIMARY KEY AUTOINCREMENT, clan_id INTEGER, uid INTEGER, amount INTEGER, timestamp INTEGER)""")
            conn.commit()
        return _db_conn

ASSETS_CATALOG = {
    "car_lada": {"name": "Лада Приора", "price": 500000, "emoji": "🚗", "income": 0},
    "car_camry": {"name": "Toyota Camry", "price": 2500000, "emoji": "🚘", "income": 0},
    "car_bmw": {"name": "BMW M5", "price": 8000000, "emoji": "🏎️", "income": 0},
    "car_porsche": {"name": "Porsche 911", "price": 15000000, "emoji": "🏎️", "income": 0},
    "car_lambo": {"name": "Lamborghini", "price": 30000000, "emoji": "🚀", "income": 0},
    "car_ferrari": {"name": "Ferrari F8", "price": 40000000, "emoji": "🐎", "income": 0},
    "car_rolls": {"name": "Rolls-Royce", "price": 60000000, "emoji": "👑", "income": 0},
    "car_bugatti": {"name": "Bugatti Chiron", "price": 150000000, "emoji": "💨", "income": 0},
    "house_flat": {"name": "Квартира в Москве", "price": 10000000, "emoji": "🏢", "income": 0},
    "house_house": {"name": "Загородный дом", "price": 25000000, "emoji": "🏡", "income": 0},
    "house_villa": {"name": "Вилла в Дубае", "price": 50000000, "emoji": "🏙️", "income": 0},
    "house_mansion": {"name": "Особняк в Лондоне", "price": 150000000, "emoji": "🏰", "income": 0},
    "house_island": {"name": "Личный остров", "price": 500000000, "emoji": "🏝️", "income": 0},
    "business_cafe": {"name": "Кофейня", "price": 25000000, "emoji": "☕", "income": 500000}, 
    "business_shop": {"name": "Магазин", "price": 50000000, "emoji": "🛒", "income": 1500000},
    "business_it": {"name": "IT-Компания", "price": 100000000, "emoji": "💻", "income": 5000000},
    "business_factory": {"name": "Завод", "price": 250000000, "emoji": "🏭", "income": 15000000},
    "business_bank": {"name": "Частный Банк", "price": 1000000000, "emoji": "🏦", "income": 50000000},
    "luxury_yacht": {"name": "Яхта", "price": 300000000, "emoji": "🛥️", "income": 0},
    "luxury_jet": {"name": "Частный самолет", "price": 500000000, "emoji": "✈️", "income": 0},
    "luxury_heli": {"name": "Вертолет", "price": 200000000, "emoji": "🚁", "income": 0}
}

HOUSE_UPGRADES = {1: {"name": "Фундамент", "price": 5000000, "desc": "Начало строительства"},2: {"name": "Гараж", "price": 15000000, "desc": "+5% к продаже машин"},3: {"name": "Сейф", "price": 50000000, "desc": "Защита 10% баланса от проигрыша"},4: {"name": "Казино-стол", "price": 150000000, "desc": "Доступ к VIP-рулетке"},5: {"name": "Особняк", "price": 500000000, "desc": "Максимальный статус и +20% к пассивному доходу"}}
CURRENCY_RATES = {"usd": {"buy": 95, "sell": 85}, "eur": {"buy": 105, "sell": 95}, "aed": {"buy": 26, "sell": 22}}
AVATARS_CATALOG = {"dog": {"emoji": "🐶", "price": 100000}, "wolf": {"emoji": "🐺", "price": 500000}, "lion": {"emoji": "🦁", "price": 1000000}, "diamond": {"emoji": "💎", "price": 5000000}, "crown": {"emoji": "👑", "price": 10000000}, "rocket": {"emoji": "🚀", "price": 20000000}, "alien": {"emoji": "👽", "price": 50000000}}
SKINS_CATALOG = {"default": {"name": "Стандарт", "price": 0, "syms": None},"space": {"name": "Космос", "price": 10000000, "syms": ['🌍','🌕','🌟','☄️','🚀','👽','🛸','🌠']},"cyber": {"name": "Киберпанк", "price": 25000000, "syms": ['💻','🔋','🔌','📡','🤖','👾','⚡','🧬']}}
FRAMES_CATALOG = {"default": {"name": "Стандарт", "price": 0, "css": "border: 2px solid #555; border-radius: 50%;"},"neon": {"name": "Неон", "price": 10000000, "css": "border: 3px solid #00ffff; border-radius: 50%; box-shadow: 0 0 15px #00ffff;"},"gold": {"name": "Золото", "price": 50000000, "css": "border: 3px solid #ffd700; border-radius: 50%; box-shadow: 0 0 15px #ffd700;"},"fire": {"name": "Огонь", "price": 150000000, "css": "border: 3px solid #ff3b30; border-radius: 50%; box-shadow: 0 0 15px #ff3b30;"}}
TECH_TREE = {"eco_income": {"name": "Экономика: Доход", "desc": "+10% к доходу с бизнеса", "price": 50000000, "max_lvl": 5, "effect": 0.10},"eco_sell": {"name": "Экономика: Продажа", "desc": "+5% к продаже имущества", "price": 100000000, "max_lvl": 3, "effect": 0.05},"lucky_scatter": {"name": "Азарт: Скаттеры", "desc": "+5% к шансу скаттеров", "price": 200000000, "max_lvl": 1, "effect": 0.05},"lucky_roulette": {"name": "Азарт: Рулетка", "desc": "+10% к выплатам в рулетке", "price": 150000000, "max_lvl": 5, "effect": 0.10},"social_ref": {"name": "Социалка: Рефералы", "desc": "+1% к реферальным отчислениям", "price": 50000000, "max_lvl": 5, "effect": 0.01},"social_clan": {"name": "Социалка: Кланы", "desc": "+5% к очкам клана", "price": 100000000, "max_lvl": 3, "effect": 0.05}}
STORY_CHAPTERS = {1: {"title": "Первая сделка", "desc": "Купи Кофейню за 25 млн", "reward_chips": 5000000, "reward_usd": 0, "req_type": "asset", "req_id": "business_cafe"},2: {"title": "Отмывание", "desc": "Купи 3 бизнеса", "reward_chips": 15000000, "reward_usd": 10, "req_type": "assets_count", "req_id": 3},3: {"title": "Влияние", "desc": "Вступи в клан", "reward_chips": 50000000, "reward_usd": 50, "req_type": "clan", "req_id": 1},4: {"title": "Теневой король", "desc": "Купи Завод", "reward_chips": 200000000, "reward_usd": 200, "req_type": "asset", "req_id": "business_factory"}}
DONATE_CATALOG = {"chips_small": {"name": "100 000 фишек", "price_stars": 50, "type": "chips", "value": 100000},"chips_medium": {"name": "1 000 000 фишек", "price_stars": 400, "type": "chips", "value": 1000000},"vip_month": {"name": "VIP на 30 дней", "price_stars": 500, "type": "vip", "value": 30},"skin_exclusive": {"name": "Эксклюзивный скин", "price_stars": 300, "type": "skin", "value": "exclusive"}}

GAMES = {
    "fruits": {"cols": 3, "rows": 1, "min_bet": 10, "symbols": [{"id":0, "pay":[0, 10, 30]}, {"id":1, "pay":[0, 15, 50]}, {"id":2, "pay":[0, 20, 100]}, {"id":3, "pay":[0, 50, 200]}, {"id":4, "pay":[0, 100, 500]}, {"id":5, "pay":[0, 200, 1000]}], "scatter": None},
    "fishing": {"cols": 5, "rows": 3, "min_bet": 10, "symbols": [{"id":0, "pay":[0, 5, 10, 25, 100]}, {"id":1, "pay":[0, 5, 10, 25, 100]}, {"id":2, "pay":[0, 5, 10, 25, 100]}, {"id":3, "pay":[0, 5, 10, 25, 100]}, {"id":4, "pay":[0, 5, 10, 25, 100]}, {"id":5, "pay":[0, 10, 20, 50, 200]}, {"id":6, "pay":[0, 20, 100, 500, 500]}, {"id":7, "pay":[0, 20, 100, 500, 500]}, {"id":8, "pay":[0, 30, 150, 1000, 1000]}, {"id":9, "pay":[5, 50, 200, 2000, 2000]}], "scatter": 10, "wild": 11, "fish_cash": [12, 13, 14, 15]}
}
LINES = {"fruits": [[0,0,0]], "fishing": [[1,1,1,1,1], [0,0,0,0,0], [2,2,2,2,2], [0,1,2,1,0], [2,1,0,1,2], [0,0,1,2,2], [2,2,1,0,0], [0,1,2,2,2], [2,1,0,0,0], [0,0,1,0,0]]}

def get_user(uid):
    conn = db()
    row = conn.execute("SELECT balance, wheel_time, wheel_daily, wheel_day, free_spins, xp, level, referrer_id, ref_count, fs_bet, last_ad, is_spinning, fish_caught, total_wilds, usd, eur, aed, last_collect, daily_streak, last_daily, avatar, ref_earnings, vip_expires, last_black_market, energy, pickaxe_lvl, active_skin, active_frame, last_energy_time FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        conn.execute("INSERT INTO users(uid, balance) VALUES(?, 5000)", (uid,))
        conn.commit()
        row = (5000, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '👤', 0, 0, 0, 1000, 1, 'default', 'default', 0)
    return {"balance": row[0], "wheel_time": row[1], "wheel_daily": row[2], "wheel_day": row[3], "free_spins": row[4], "xp": row[5], "level": row[6], "referrer_id": row[7], "ref_count": row[8], "fs_bet": row[9], "last_ad": row[10], "is_spinning": row[11], "fish_caught": row[12], "total_wilds": row[13], "usd": row[14], "eur": row[15], "aed": row[16], "last_collect": row[17], "daily_streak": row[18], "last_daily": row[19], "avatar": row[20], "ref_earnings": row[21], "vip_expires": row[22], "last_black_market": row[23], "energy": row[24], "pickaxe_lvl": row[25], "active_skin": row[26], "active_frame": row[27], "last_energy_time": row[28]}

def set_user(uid, **kw):
    for k in kw:
        if k not in ALLOWED_USER_COLUMNS:
            raise ValueError(f"Недопустимая колонка: {k}")
    conn = db()
    for k, v in kw.items(): conn.execute(f"UPDATE users SET {k}=? WHERE uid=?", (v, uid))
    conn.commit()

def verify(init_data: str) -> dict:
    if not BOT_TOKEN: raise HTTPException(500, "BOT_TOKEN не задан")
    try: p = dict(parse_qsl(init_data, strict_parsing=True))
    except: raise HTTPException(400, "bad init_data")
    h = p.pop("hash", None)
    if not h: raise HTTPException(400, "no hash")
    try: auth_date = int(p.get("auth_date", 0))
    except (ValueError, TypeError): raise HTTPException(400, "bad auth_date")
    if auth_date == 0 or time.time() - auth_date > 3600: raise HTTPException(401, "init_data expired")
    check = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), h): raise HTTPException(401, "bad signature")
    return json.loads(p["user"])

def get_tech_bonus(uid, node_id):
    conn = db()
    row = conn.execute("SELECT level FROM tech_tree WHERE uid=? AND node_id=?", (uid, node_id)).fetchone()
    if not row: return 0.0
    return TECH_TREE[node_id]["effect"] * row[0]

def generate_grid(game_key, is_bonus=False, current_wilds=0, is_first_fs=False):
    g = GAMES[game_key]
    cols, rows = g["cols"], g["rows"]
    grid = [[None]*rows for _ in range(cols)]
    fish_prices = {}
    if game_key == "fishing":
        wild_chance = 0.0
        if is_bonus:
            if is_first_fs: wild_chance = 0.0
            else:
                if current_wilds < 3: wild_chance = 0.02
                elif current_wilds < 6: wild_chance = 0.03
                elif current_wilds < 9: wild_chance = 0.04
                elif current_wilds < 12: wild_chance = 0.05
                else: wild_chance = 0.06
        else: wild_chance = 0.07
        for col_idx in range(cols):
            for r_idx in range(rows):
                rand = random.random()
                if rand < 0.01: grid[col_idx][r_idx] = g["scatter"]
                elif rand < (0.20 if is_bonus else 0.05): 
                    grid[col_idx][r_idx] = random.choice(g["fish_cash"]); 
                    fish_prices[(col_idx, r_idx)] = random.choice([2, 5, 10, 15, 20, 25, 50, 200])
                elif rand < (0.20 + wild_chance): grid[col_idx][r_idx] = g["wild"]
                else: grid[col_idx][r_idx] = random.choice(range(10))
        return grid, fish_prices
    weights = [70, 60, 50, 40, 20, 5]
    pool = [s["id"] for s in g["symbols"] for _ in range(weights[s["id"]] if s["id"] < len(weights) else 1)]
    for col_idx in range(cols):
        col = []
        for _ in range(rows):
            if g["scatter"] is not None and random.random() < 0.02: col.append(g["scatter"])
            else: col.append(random.choice(pool))
        grid[col_idx] = col
    return grid, fish_prices

def check_win(grid, game_key, bet, fish_prices, fish_caught=0, total_wilds=0):
    g = GAMES[game_key]; lines = LINES[game_key]; total_win = 0; win_lines = []; scatters = 0; wilds_count = 0; fish_data = []
    if g.get("scatter") is not None:
        for col in grid:
            for sym in col:
                if sym == g["scatter"]: scatters += 1
    if game_key == "fishing":
        wild_coords = [(col_idx, r_idx) for col_idx in range(len(grid)) for r_idx in range(len(grid[col_idx])) if grid[col_idx][r_idx] == g["wild"]]
        wilds_count = len(wild_coords)
        if wilds_count >= 1:
            mult = 1
            if total_wilds >= 12: mult = 10
            elif total_wilds >= 8: mult = 5
            elif total_wilds >= 4: mult = 2
            for col_idx in range(len(grid)):
                for r_idx in range(len(grid[col_idx])):
                    if grid[col_idx][r_idx] in g["fish_cash"]:
                        if random.random() < 0.5:
                            price_mult = fish_prices.get((col_idx, r_idx), 2)
                            val = price_mult * bet
                            total_win += val * mult
                            fish_data.append({"col": col_idx, "row": r_idx, "val": val, "mult": mult})
                        else:
                            fish_data.append({"col": col_idx, "row": r_idx, "val": 0, "mult": 1})
    for line_idx, line in enumerate(lines):
        first_sym = grid[0][line[0]]
        if first_sym is None or first_sym >= 10: continue
        count = 1
        for col_idx in range(1, len(grid)):
            sym = grid[col_idx][line[col_idx]]
            if sym == first_sym or (game_key == "fishing" and sym == g["wild"]): count += 1
            elif first_sym == g.get("wild") and game_key == "fishing": 
                first_sym = sym; count += 1
            else: break
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
@app.post("/bonus")
def bonus(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if now < d["wheel_time"]: raise HTTPException(400, f"Кулдаун! Ждать: {((d['wheel_time'] - now) // 60)} мин.")
    rnd = random.random() * 100
    if rnd < 1: amount = 1000000
    elif rnd < 4: amount = 500000
    elif rnd < 12: amount = 100000
    elif rnd < 32: amount = 25000
    elif rnd < 62: amount = 5000
    elif rnd < 87: amount = 1000
    else: amount = 0
    set_user(uid, balance=d["balance"] + amount, wheel_time=now + 86400)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.post("/ad_energy")
def ad_energy(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    boost = 300
    new_energy = min(1000, d["energy"] + boost)
    set_user(uid, energy=new_energy, last_ad=now)
    return {"status": "ok", "energy": new_energy, "boost": boost}

@app.post("/get_assets")
def get_assets(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    rows = conn.execute("SELECT id, item_id, buy_price FROM assets WHERE uid=?", (uid,)).fetchall()
    assets = []; total_value = 0
    for r_id, item_id, price in rows:
        item = ASSETS_CATALOG.get(item_id, {"name": "Неизвестно", "price": 0, "emoji": "❓"})
        assets.append({"id": r_id, "item_id": item_id, "name": item["name"], "emoji": item["emoji"], "price": price})
        total_value += price
    return {"assets": assets, "total_value": total_value}

@app.post("/get_shop_rotation")
def get_shop_rotation(r: Req):
    u = verify(r.init_data); uid = u["id"]; now = int(time.time())
    day_seed = now // 86400
    random.seed(day_seed)
    all_items = list(ASSETS_CATALOG.keys())
    shop_items = random.sample(all_items, min(8, len(all_items)))
    next_update = (day_seed + 1) * 86400
    result = []
    for item_id in shop_items:
        data = ASSETS_CATALOG[item_id]
        result.append({"id": item_id, "name": data["name"], "price": data["price"], "emoji": data["emoji"], "income": data["income"]})
    return {"items": result, "time_left": next_update - now}

@app.post("/buy_asset")
def buy_asset(r: BuyAssetReq):
    u = verify(r.init_data); uid = u["id"]
    item = ASSETS_CATALOG.get(r.item_id)
    if not item: raise HTTPException(400, "Товар не найден")
    conn = db()
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (item["price"], uid, item["price"]))
    if cur.rowcount == 0:
        conn.rollback()
        raise HTTPException(400, "Недостаточно фишек")
    conn.execute("INSERT INTO assets(uid, item_id, buy_price, buy_time) VALUES(?,?,?,?)", (uid, r.item_id, item["price"], int(time.time())))
    conn.commit()
    new_bal = get_user(uid)["balance"]
    return {"status": "ok", "balance": new_bal, "message": f"Вы купили {item['name']}!"}

@app.post("/sell_asset")
def sell_asset(r: BuyAssetReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT item_id, buy_price FROM assets WHERE id=? AND uid=?", (int(r.item_id), uid)).fetchone()
    if not row: raise HTTPException(400, "Имущество не найдено")
    item_id, buy_price = row
    sell_rate = 0.7 + get_tech_bonus(uid, "eco_sell")
    house_row = conn.execute("SELECT level FROM player_house WHERE uid=?", (uid,)).fetchone()
    if house_row and house_row[0] >= 2 and item_id.startswith("car_"):
        sell_rate += 0.05
    refund = int(buy_price * min(sell_rate, 1.0))
    conn.execute("DELETE FROM assets WHERE id=? AND uid=?", (int(r.item_id), uid))
    conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (refund, uid))
    conn.commit()
    new_bal = get_user(uid)["balance"]
    return {"status": "ok", "balance": new_bal, "message": f"Вы продали за {refund} фишек"}

@app.post("/collect_income")
def collect_income(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    last_collect = d.get("last_collect", 0)
    conn = db()
    if last_collect == 0:
        first_buy = conn.execute("SELECT MIN(buy_time) FROM assets WHERE uid=?", (uid,)).fetchone()[0]
        last_collect = first_buy if first_buy else now
        set_user(uid, last_collect=last_collect)
    time_passed = min(now - last_collect, 18000)
    if time_passed < 3600: raise HTTPException(400, f"Ждать: {((3600 - time_passed) // 60)} мин.")
    rows = conn.execute("SELECT item_id FROM assets WHERE uid=?", (uid,)).fetchall()
    total_income_per_hour = sum(ASSETS_CATALOG.get(item_id, {}).get("income", 0) for (item_id,) in rows)
    if total_income_per_hour == 0: raise HTTPException(400, "Нет бизнеса")
    hours = int(time_passed // 3600)
    total_income = total_income_per_hour * hours
    house_row = conn.execute("SELECT level FROM player_house WHERE uid=?", (uid,)).fetchone()
    if house_row and house_row[0] >= 5: total_income = int(total_income * 1.2)
    tech_bonus = get_tech_bonus(uid, "eco_income")
    if tech_bonus > 0: total_income = int(total_income * (1 + tech_bonus))
    conn.execute("UPDATE users SET balance = balance + ?, last_collect=? WHERE uid=?", (total_income, now, uid))
    conn.commit()
    new_bal = get_user(uid)["balance"]
    return {"status": "ok", "amount": total_income, "hours": hours, "balance": new_bal}

@app.post("/exchange")
def exchange(r: ExchangeReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if r.currency not in CURRENCY_RATES: raise HTTPException(400, "Валюта не поддерживается")
    if r.amount <= 0: raise HTTPException(400, "Сумма > 0")
    rate = CURRENCY_RATES[r.currency]
    conn = db()
    if r.action == 'sell':
        current_wallet = d.get(r.currency, 0)
        if current_wallet < r.amount: raise HTTPException(400, "Мало валюты")
        gain = r.amount * rate["sell"]
        cur = conn.execute(f"UPDATE users SET {r.currency} = {r.currency} - ? WHERE uid=? AND {r.currency} >= ?", (r.amount, uid, r.amount))
        if cur.rowcount == 0: raise HTTPException(400, "Мало валюты")
        conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (gain, uid))
        conn.commit()
        d = get_user(uid)
        return {"status": "ok", "balance": d["balance"], "wallet": d[r.currency]}
    raise HTTPException(400, "Покупка валюты недоступна")

@app.post("/get_house")
def get_house(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT level FROM player_house WHERE uid=?", (uid,)).fetchone()
    level = row[0] if row else 0
    upgrades = []
    for lvl, data in HOUSE_UPGRADES.items():
        upgrades.append({"level": lvl, "name": data["name"], "price": data["price"], "desc": data["desc"], "is_bought": level >= lvl, "can_buy": level == lvl - 1})
    return {"my_level": level, "upgrades": upgrades}

@app.post("/buy_house_upgrade")
def buy_house_upgrade(r: HouseReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    conn = db()
    row = conn.execute("SELECT level FROM player_house WHERE uid=?", (uid,)).fetchone()
    level = row[0] if row else 0
    next_lvl = level + 1
    if next_lvl not in HOUSE_UPGRADES: raise HTTPException(400, "Дом уже максимального уровня")
    upgrade = HOUSE_UPGRADES[next_lvl]
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (upgrade["price"], uid, upgrade["price"]))
    if cur.rowcount == 0: raise HTTPException(400, f"Нужно {upgrade['price']} фишек")
    if level == 0: conn.execute("INSERT INTO player_house(uid, level) VALUES(?, ?)", (uid, next_lvl))
    else: conn.execute("UPDATE player_house SET level=? WHERE uid=?", (next_lvl, uid))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "level": next_lvl, "message": f"Построено: {upgrade['name']}!"}

@app.post("/open_case")
def open_case(r: Req):
    u = verify(r.init_data); uid = u["id"]
    COST = 50000
    conn = db()
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (COST, uid, COST))
    if cur.rowcount == 0: raise HTTPException(400, f"Нужно {COST} фишек")
    conn.commit()
    rnd = random.random() * 100
    prize_type = ""; prize_value = 0; prize_text = ""
    if rnd < 1: prize_type = "car_lambo"; prize_text = "🚀 Lamborghini!"
    elif rnd < 5: prize_type = "usd"; prize_value = 10; prize_text = "💵 10 USD"
    elif rnd < 15: prize_type = "chips"; prize_value = 500000; prize_text = "💰 500 000 фишек"
    elif rnd < 40: prize_type = "chips"; prize_value = 100000; prize_text = "💰 100 000 фишек"
    elif rnd < 70: prize_type = "chips"; prize_value = 50000; prize_text = "💰 50 000 фишек"
    else: prize_type = "empty"; prize_text = "😢 Пусто"
    return {"status": "ok", "prize_type": prize_type, "prize_value": prize_value, "prize_text": prize_text, "balance": get_user(uid)["balance"]}

@app.post("/claim_case_prize")
def claim_case_prize(r: ClaimPrizeReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    conn = db()
    if r.prize_type == "car_lambo":
        conn.execute("INSERT INTO assets(uid, item_id, buy_price, buy_time) VALUES(?,?,?,?)", (uid, "car_lambo", 15000000, now))
    elif r.prize_type == "usd":
        conn.execute("UPDATE users SET usd = usd + ? WHERE uid=?", (r.prize_value, uid))
    elif r.prize_type == "chips":
        conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (r.prize_value, uid))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"]}

@app.post("/create_clan")
def create_clan(r: CreateClanReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    COST = 1000000
    conn = db()
    existing = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if existing: raise HTTPException(400, "Вы уже в клане")
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (COST, uid, COST))
    if cur.rowcount == 0: raise HTTPException(400, "Нужно 1 000 000")
    try:
        conn.execute("INSERT INTO clans(name, owner_id) VALUES(?, ?)", (r.name, uid))
        clan_id = conn.lastrowid
        conn.execute("INSERT INTO clan_members(uid, clan_id, role) VALUES(?, ?, 'owner')", (uid, clan_id))
        conn.commit()
        return {"status": "ok", "balance": get_user(uid)["balance"], "message": "Клан создан!"}
    except sqlite3.IntegrityError:
        conn.rollback()
        raise HTTPException(400, "Название занято")

@app.post("/get_clans")
def get_clans(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    my_clan = conn.execute("SELECT clan_id, role FROM clan_members WHERE uid=?", (uid,)).fetchone()
    clans = conn.execute("SELECT id, name, total_score FROM clans ORDER BY total_score DESC LIMIT 20").fetchall()
    my_data = None
    if my_clan:
        cid, role = my_clan
        row = conn.execute("SELECT id, name, total_score FROM clans WHERE id=?", (cid,)).fetchone()
        if row:
            members = conn.execute("SELECT COUNT(*) FROM clan_members WHERE clan_id=?", (cid,)).fetchone()[0]
            my_data = {"id": row[0], "name": row[1], "score": row[2], "members": members, "role": role}
    return {"my_clan": my_data, "top_clans": [{"id": r[0], "name": r[1], "score": r[2]} for r in clans]}

@app.post("/join_clan")
def join_clan(r: JoinClanReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    existing = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if existing: raise HTTPException(400, "Вы уже в клане")
    clan = conn.execute("SELECT id FROM clans WHERE id=?", (r.clan_id,)).fetchone()
    if not clan: raise HTTPException(400, "Клан не найден")
    conn.execute("INSERT INTO clan_members(uid, clan_id) VALUES(?, ?)", (uid, r.clan_id))
    conn.commit()
    return {"status": "ok"}

@app.post("/leave_clan")
def leave_clan(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    member = conn.execute("SELECT clan_id, role FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if not member: raise HTTPException(400, "Вы не в клане")
    cid, role = member
    if role == 'owner': conn.execute("DELETE FROM clans WHERE id=?", (cid,))
    conn.execute("DELETE FROM clan_members WHERE uid=?", (uid,))
    conn.commit()
    return {"status": "ok"}

@app.post("/clan_war_state")
def clan_war_state(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    war = conn.execute("SELECT id, clan1_id, clan2_id, start_time, end_time, clan1_score, clan2_score FROM clan_wars WHERE status='active'").fetchone()
    if not war: return {"active": False}
    clan1 = conn.execute("SELECT name FROM clans WHERE id=?", (war[1],)).fetchone()
    clan2 = conn.execute("SELECT name FROM clans WHERE id=?", (war[2],)).fetchone()
    return {"active": True, "clan1_name": clan1[0] if clan1 else "Удален", "clan1_score": war[5], "clan2_name": clan2[0] if clan2 else "Удален", "clan2_score": war[6], "end_time": war[4]}

@app.post("/tournament")
def get_tournament(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    rows = conn.execute("SELECT t.uid, t.score, u.avatar FROM tournament t JOIN users u ON t.uid = u.uid ORDER BY t.score DESC LIMIT 10").fetchall()
    my_score_row = conn.execute("SELECT score FROM tournament WHERE uid=?", (uid,)).fetchone()
    my_score = my_score_row[0] if my_score_row else 0
    top = [{"rank": i+1, "name": f"{str(r[0])[:3]}***{str(r[0])[-2:]}", "score": r[1], "avatar": r[2] or '👤'} for i, r in enumerate(rows)]
    return {"top": top, "my_score": my_score}

@app.post("/rating")
def rating(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    query = """
    SELECT u.uid, u.balance, u.avatar, COALESCE(SUM(a.buy_price), 0) as assets_value,
           (u.balance + COALESCE(SUM(a.buy_price), 0)) as total_capital, u.vip_expires,
           COALESCE(ph.level, 0) as house_level, u.active_frame
    FROM users u LEFT JOIN assets a ON u.uid = a.uid LEFT JOIN player_house ph ON u.uid = ph.uid
    GROUP BY u.uid ORDER BY total_capital DESC LIMIT 10
    """
    rows = conn.execute(query).fetchall()
    top = [{"rank": i+1, "name": f"{str(r[0])[:3]}***{str(r[0])[-2:]}", "balance": r[1], "assets": r[3], "capital": r[4], "avatar": r[2] or '👤', "is_vip": (r[5] or 0) > int(time.time()), "house_level": r[6] or 0, "active_frame": r[7] or 'default'} for i, r in enumerate(rows)]
    return {"top": top}

@app.post("/jackpot")
def get_jackpot(r: Req):
    conn = db()
    row = conn.execute("SELECT amount FROM global_jackpot WHERE id=1").fetchone()
    return {"amount": row[0] if row else 0}

@app.post("/redeem_promo")
def redeem_promo(r: PromoReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT reward, uses_left FROM promocodes WHERE code=?", (r.code.upper(),)).fetchone()
    if not row: raise HTTPException(400, "Неверный промокод")
    reward, uses = row
    if uses <= 0: raise HTTPException(400, "Промокод больше не действителен")
    existing = conn.execute("SELECT 1 FROM promo_activations WHERE uid=? AND code=?", (uid, r.code.upper())).fetchone()
    if existing: raise HTTPException(400, "Вы уже активировали этот код")
    conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (reward, uid))
    conn.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code=?", (r.code.upper(),))
    conn.execute("INSERT INTO promo_activations(uid, code) VALUES(?, ?)", (uid, r.code.upper()))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "reward": reward}

@app.post("/get_market")
def get_market(r: Req):
    conn = db()
    rows = conn.execute("SELECT item_id, current_price FROM market_rates").fetchall()
    rates = {row[0]: row[1] for row in rows}
    if not rates:
        for k, v in ASSETS_CATALOG.items():
            conn.execute("INSERT INTO market_rates(item_id, current_price) VALUES(?, ?)", (k, v["price"]))
            rates[k] = v["price"]
        conn.commit()
    return {"rates": rates}

@app.post("/trade_asset")
def trade_asset(r: BuyAssetReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT item_id, buy_price FROM assets WHERE id=? AND uid=?", (int(r.item_id), uid)).fetchone()
    if not row: raise HTTPException(400, "Имущество не найдено")
    item_id, buy_price = row
    market_row = conn.execute("SELECT current_price FROM market_rates WHERE item_id=?", (item_id,)).fetchone()
    current_price = market_row[0] if market_row else ASSETS_CATALOG.get(item_id, {"price": buy_price})["price"]
    sell_rate = 0.7 + get_tech_bonus(uid, "eco_sell")
    refund = int(current_price * min(sell_rate, 1.0))
    conn.execute("DELETE FROM assets WHERE id=? AND uid=?", (int(r.item_id), uid))
    conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (refund, uid))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "message": f"Продано за {refund} фишек"}

@app.post("/crypto_state")
def crypto_state(r: Req):
    u = verify(r.init_data); uid = u["id"]; now = int(time.time())
    conn = db()
    market = conn.execute("SELECT price, last_update FROM crypto_market WHERE id=1").fetchone()
    price, last_update = market
    if now - last_update > 1800:
        change = random.uniform(-0.2, 0.3)
        new_price = max(10.0, price * (1 + change))
        conn.execute("UPDATE crypto_market SET price=?, last_update=? WHERE id=1", (new_price, now))
        conn.commit()
        price = new_price
    crypto_row = conn.execute("SELECT tim_balance FROM crypto WHERE uid=?", (uid,)).fetchone()
    tim_balance = crypto_row[0] if crypto_row else 0.0
    return {"price": round(price, 2), "tim_balance": round(tim_balance, 4)}

@app.post("/crypto_trade")
def crypto_trade(r: CryptoReq):
    u = verify(r.init_data); uid = u["id"]; now = int(time.time())
    if r.amount <= 0: raise HTTPException(400, "Сумма > 0")
    conn = db()
    price = conn.execute("SELECT price FROM crypto_market WHERE id=1").fetchone()[0]
    d = get_user(uid)
    crypto_row = conn.execute("SELECT tim_balance FROM crypto WHERE uid=?", (uid,)).fetchone()
    tim_balance = crypto_row[0] if crypto_row else 0.0
    if r.action == 'buy':
        cost = int(r.amount * price)
        cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (cost, uid, cost))
        if cur.rowcount == 0: raise HTTPException(400, "Мало фишек")
        new_tim = tim_balance + r.amount
        if crypto_row: conn.execute("UPDATE crypto SET tim_balance=? WHERE uid=?", (new_tim, uid))
        else: conn.execute("INSERT INTO crypto(uid, tim_balance) VALUES(?, ?)", (uid, new_tim))
        conn.commit()
        return {"status": "ok", "balance": get_user(uid)["balance"], "tim_balance": round(new_tim, 4), "message": "Куплено!"}
    elif r.action == 'sell':
        if tim_balance < r.amount: raise HTTPException(400, "Мало TIM")
        gain = int(r.amount * price)
        new_tim = tim_balance - r.amount
        conn.execute("UPDATE crypto SET tim_balance=? WHERE uid=?", (new_tim, uid))
        conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (gain, uid))
        conn.commit()
        return {"status": "ok", "balance": get_user(uid)["balance"], "tim_balance": round(new_tim, 4), "message": "Продано!"}
    raise HTTPException(400, "Неверное действие")

@app.post("/black_market")
def get_black_market(r: Req):
    u = verify(r.init_data); uid = u["id"]; now = int(time.time())
    conn = db()
    conn.execute("DELETE FROM black_market WHERE expires_at < ?", (now,))
    items = conn.execute("SELECT id, item_name, description, price, reward_value, risk_chance FROM black_market").fetchall()
    if len(items) < 3:
        conn.execute("DELETE FROM black_market")
        possible = [("Украденный iPhone", "Контрабанда.", 50000, 58000, 0.15),("Подпольное казино", "Доход.", 500000, 580000, 0.20),("Фальшивые дирхамы", "Грязный курс.", 10000, 11000, 0.10)]
        for name, desc, price, reward, risk in possible:
            conn.execute("INSERT INTO black_market(item_name, description, price, reward_value, risk_chance, expires_at) VALUES(?,?,?,?,?,?)", (name, desc, price, reward, risk, now + 3600))
        conn.commit()
        items = conn.execute("SELECT id, item_name, description, price, reward_value, risk_chance FROM black_market").fetchall()
    return {"items": [{"id": r[0], "name": r[1], "desc": r[2], "price": r[3], "reward": r[4], "risk": r[5]} for r in items]}

@app.post("/black_buy")
def black_buy(r: BlackMarketReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if now - d["last_black_market"] < 1800: raise HTTPException(400, f"Ждать {1800 - (now - d['last_black_market'])} сек.")
    conn = db()
    item = conn.execute("SELECT item_name, price, reward_value, risk_chance FROM black_market WHERE id=?", (r.item_id,)).fetchone()
    if not item: raise HTTPException(400, "Товар пропал")
    name, price, reward, risk = item
    cur = conn.execute("UPDATE users SET balance = balance - ?, last_black_market=? WHERE uid=? AND balance >= ?", (price, now, uid, price))
    if cur.rowcount == 0: raise HTTPException(400, "Мало фишек")
    is_busted = random.random() < risk
    if is_busted: msg = f"🚨 Провал! {name}."
    else:
        conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (reward, uid))
        msg = f"✅ Успех! {name} +{reward}."
    conn.execute("DELETE FROM black_market WHERE id=?", (r.item_id,))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "message": msg, "busted": is_busted}

@app.post("/chat_send")
def chat_send(r: ChatSendReq):
    u = verify(r.init_data); uid = u["id"]
    if not r.text.strip(): raise HTTPException(400, "Пусто")
    if len(r.text) > 100: raise HTTPException(400, "Длинно")
    now = int(time.time())
    conn = db()
    last_msg = conn.execute("SELECT timestamp FROM chat_messages WHERE uid=? ORDER BY timestamp DESC LIMIT 1", (uid,)).fetchone()
    if last_msg and now - last_msg[0] < 3: raise HTTPException(400, "Ждать 3 сек")
    clan_id = 0
    if r.is_clan:
        member = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
        if not member: raise HTTPException(400, "Не в клане")
        clan_id = member[0]
    conn.execute("INSERT INTO chat_messages(uid, clan_id, text, timestamp) VALUES(?,?,?,?)", (uid, clan_id, r.text.strip(), now))
    conn.commit()
    return {"status": "ok"}

@app.post("/chat_get")
def chat_get(r: ChatGetReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    if r.is_clan:
        member = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
        if not member: return {"messages": []}
        rows = conn.execute("""SELECT m.id, m.uid, m.text, m.timestamp, CASE WHEN m.uid = 0 THEN '🤖' ELSE u.avatar END as avatar FROM chat_messages m LEFT JOIN users u ON m.uid = u.uid WHERE m.clan_id = ? AND m.id > ? ORDER BY m.id ASC LIMIT 50""", (member[0], r.last_id)).fetchall()
    else:
        rows = conn.execute("""SELECT m.id, m.uid, m.text, m.timestamp, CASE WHEN m.uid = 0 THEN '🤖' ELSE u.avatar END as avatar FROM chat_messages m LEFT JOIN users u ON m.uid = u.uid WHERE m.clan_id = 0 AND m.id > ? ORDER BY m.id ASC LIMIT 50""", (r.last_id,)).fetchall()
    msgs = []
    for row in rows:
        name = "СИСТЕМА" if row[1] == 0 else f"{str(row[1])[:3]}***{str(row[1])[-2:]}"
        msgs.append({"id": row[0], "name": name, "text": row[2], "time": row[3], "avatar": row[4] or '👤', "uid": row[1]})
    return {"messages": msgs}

@app.post("/get_mine")
def get_mine(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    time_passed = now - d["last_energy_time"]
    if time_passed > 0:
        energy_regen = time_passed // 60
        new_energy = min(1000, d["energy"] + energy_regen)
        if new_energy != d["energy"]:
            set_user(uid, energy=new_energy, last_energy_time=now)
            d["energy"] = new_energy
    return {"energy": d["energy"], "pickaxe_lvl": d["pickaxe_lvl"], "tap_power": d["pickaxe_lvl"] * 10, "max_energy": 1000}

@app.post("/tap")
def tap(r: TapReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if r.taps <= 0: raise HTTPException(400, "Некорректно")
    if d["energy"] < r.taps: raise HTTPException(400, "Мало энергии")
    reward = r.taps * (d["pickaxe_lvl"] * 10)
    conn = db()
    cur = conn.execute("UPDATE users SET energy = energy - ?, balance = balance + ?, last_energy_time=? WHERE uid=? AND energy >= ?", (r.taps, reward, now, uid, r.taps))
    if cur.rowcount == 0: raise HTTPException(400, "Мало энергии")
    row_q = conn.execute("SELECT 1 FROM quests WHERE uid=?", (uid,)).fetchone()
    if row_q: conn.execute("UPDATE quests SET taps_count = taps_count + ?, mine_earned = mine_earned + ? WHERE uid=?", (r.taps, reward, uid))
    conn.commit()
    d = get_user(uid)
    return {"status": "ok", "balance": d["balance"], "energy": d["energy"], "reward": reward}

@app.post("/upgrade_pickaxe")
def upgrade_pickaxe(r: UpgradePickReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    upgrade_cost = d["pickaxe_lvl"] * 50000
    conn = db()
    cur = conn.execute("UPDATE users SET balance = balance - ?, pickaxe_lvl = pickaxe_lvl + 1 WHERE uid=? AND balance >= ?", (upgrade_cost, uid, upgrade_cost))
    if cur.rowcount == 0: raise HTTPException(400, f"Нужно {upgrade_cost} фишек")
    conn.execute("UPDATE quests SET pickaxe_upgrades = pickaxe_upgrades + 1 WHERE uid=?", (uid,))
    conn.commit()
    d = get_user(uid)
    return {"status": "ok", "balance": d["balance"], "pickaxe_lvl": d["pickaxe_lvl"], "message": f"Кирка ур. {d['pickaxe_lvl']}!"}

@app.post("/get_donate")
def get_donate(r: Req):
    return {"items": [{"id": k, "name": v["name"], "price": v["price_stars"], "type": v["type"]} for k, v in DONATE_CATALOG.items()]}

@app.post("/create_invoice")
def create_invoice(r: DonateReq):
    item = DONATE_CATALOG.get(r.item_id)
    if not item: raise HTTPException(400, "Не найден")
    return {"status": "ok", "item_id": r.item_id, "title": item["name"], "price": item["price_stars"]}

@app.post("/check_payment")
def check_payment(r: CheckPayReq):
    raise HTTPException(403, "Оплата недоступна.")

@app.post("/get_tech")
def get_tech(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    my_techs = conn.execute("SELECT node_id, level FROM tech_tree WHERE uid=?", (uid,)).fetchall()
    tech_dict = {row[0]: row[1] for row in my_techs}
    result = []
    for node_id, data in TECH_TREE.items():
        current_lvl = tech_dict.get(node_id, 0)
        next_price = int(data["price"] * (1 + current_lvl * 0.5))
        result.append({"id": node_id, "name": data["name"], "desc": data["desc"], "current_lvl": current_lvl, "max_lvl": data["max_lvl"], "price": next_price, "can_buy": current_lvl < data["max_lvl"]})
    return {"techs": result}

@app.post("/buy_tech")
def buy_tech(r: TechReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    conn = db()
    tech = TECH_TREE.get(r.node_id)
    if not tech: raise HTTPException(400, "Не найдено")
    current = conn.execute("SELECT level FROM tech_tree WHERE uid=? AND node_id=?", (uid, r.node_id)).fetchone()
    current_lvl = current[0] if current else 0
    if current_lvl >= tech["max_lvl"]: raise HTTPException(400, "Максимум")
    price = int(tech["price"] * (1 + current_lvl * 0.5))
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (price, uid, price))
    if cur.rowcount == 0: raise HTTPException(400, "Мало фишек")
    if current: conn.execute("UPDATE tech_tree SET level = level + 1 WHERE uid=? AND node_id=?", (uid, r.node_id))
    else: conn.execute("INSERT INTO tech_tree(uid, node_id, level) VALUES(?, ?, 1)", (uid, r.node_id))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "message": "Технология улучшена!"}

@app.post("/get_story")
def get_story(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT chapter FROM story_progress WHERE uid=?", (uid,)).fetchone()
    my_chapter = row[0] if row else 0
    assets_count = conn.execute("SELECT COUNT(*) FROM assets WHERE uid=?", (uid,)).fetchone()[0]
    has_clan = conn.execute("SELECT 1 FROM clan_members WHERE uid=?", (uid,)).fetchone() is not None
    user_assets = [r[0] for r in conn.execute("SELECT item_id FROM assets WHERE uid=?", (uid,)).fetchall()]
    chapters = []
    for ch_id, ch_data in STORY_CHAPTERS.items():
        is_completed = False
        if ch_data["req_type"] == "asset": is_completed = ch_data["req_id"] in user_assets
        elif ch_data["req_type"] == "assets_count": is_completed = assets_count >= ch_data["req_id"]
        elif ch_data["req_type"] == "clan": is_completed = has_clan
        chapters.append({"id": ch_id, "title": ch_data["title"], "desc": ch_data["desc"], "is_completed": is_completed, "is_claimed": my_chapter >= ch_id, "reward_chips": ch_data["reward_chips"], "reward_usd": ch_data["reward_usd"]})
    return {"chapters": chapters, "my_chapter": my_chapter}

@app.post("/claim_story")
def claim_story(r: StoryClaimReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    conn = db()
    row = conn.execute("SELECT chapter FROM story_progress WHERE uid=?", (uid,)).fetchone()
    my_chapter = row[0] if row else 0
    if my_chapter >= r.chapter_id: raise HTTPException(400, "Уже пройдено")
    if r.chapter_id != my_chapter + 1: raise HTTPException(400, "Сначала предыдущую")
    ch_data = STORY_CHAPTERS.get(r.chapter_id)
    if not ch_data: raise HTTPException(400, "Нет главы")
    assets_count = conn.execute("SELECT COUNT(*) FROM assets WHERE uid=?", (uid,)).fetchone()[0]
    has_clan = conn.execute("SELECT 1 FROM clan_members WHERE uid=?", (uid,)).fetchone() is not None
    user_assets = [r[0] for r in conn.execute("SELECT item_id FROM assets WHERE uid=?", (uid,)).fetchall()]
    is_completed = False
    if ch_data["req_type"] == "asset": is_completed = ch_data["req_id"] in user_assets
    elif ch_data["req_type"] == "assets_count": is_completed = assets_count >= ch_data["req_id"]
    elif ch_data["req_type"] == "clan": is_completed = has_clan
    if not is_completed: raise HTTPException(400, "Условие не выполнено")
    conn.execute("UPDATE users SET balance = balance + ?, usd = usd + ? WHERE uid=?", (ch_data["reward_chips"], ch_data["reward_usd"], uid))
    if my_chapter == 0: conn.execute("INSERT INTO story_progress(uid, chapter) VALUES(?, ?)", (uid, r.chapter_id))
    else: conn.execute("UPDATE story_progress SET chapter=? WHERE uid=?", (r.chapter_id, uid))
    conn.commit()
    d = get_user(uid)
    return {"status": "ok", "balance": d["balance"], "usd": d["usd"], "message": f"Глава {r.chapter_id} пройдена!"}

@app.post("/get_predictions")
def get_predictions(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    now = int(time.time())
    if conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0:
        conn.execute("INSERT INTO predictions(question, option_yes, option_no, end_time) VALUES(?, ?, ?, ?)", ("Джекпот?", "Да", "Нет", now + 86400 * 7))
        conn.execute("INSERT INTO predictions(question, option_yes, option_no, end_time) VALUES(?, ?, ?, ?)", ("TimCoin > 200?", "Да", "Нет", now + 86400 * 3))
        conn.commit()
    conn.execute("UPDATE predictions SET result = CASE WHEN RANDOM() % 2 = 0 THEN 'yes' ELSE 'no' END WHERE result IS NULL AND end_time < ?", (now,))
    conn.commit()
    rows = conn.execute("SELECT id, question, option_yes, option_no, end_time, result FROM predictions ORDER BY end_time ASC").fetchall()
    preds = []
    for row in rows:
        pool_yes = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM prediction_bets WHERE prediction_id=? AND choice='yes'", (row[0],)).fetchone()[0]
        pool_no = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM prediction_bets WHERE prediction_id=? AND choice='no'", (row[0],)).fetchone()[0]
        my_bet = conn.execute("SELECT choice, amount FROM prediction_bets WHERE prediction_id=? AND uid=?", (row[0], uid)).fetchone()
        preds.append({"id": row[0], "question": row[1], "yes_text": row[2], "no_text": row[3], "end_time": row[4], "result": row[5], "pool_yes": pool_yes, "pool_no": pool_no, "my_bet": {"choice": my_bet[0], "amount": my_bet[1]} if my_bet else None})
    return {"predictions": preds}

@app.post("/bet_prediction")
def bet_prediction(r: PredBetReq):
    u = verify(r.init_data); uid = u["id"]; now = int(time.time())
    conn = db()
    pred = conn.execute("SELECT end_time, result FROM predictions WHERE id=?", (r.prediction_id,)).fetchone()
    if not pred or pred[0] < now or pred[1] is not None: raise HTTPException(400, "Недоступно")
    if r.amount <= 0 or r.choice not in ["yes", "no"]: raise HTTPException(400, "Ошибка")
    existing = conn.execute("SELECT 1 FROM prediction_bets WHERE prediction_id=? AND uid=?", (r.prediction_id, uid)).fetchone()
    if existing: raise HTTPException(400, "Уже ставили")
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (r.amount, uid, r.amount))
    if cur.rowcount == 0: raise HTTPException(400, "Мало фишек")
    conn.execute("INSERT INTO prediction_bets(uid, prediction_id, choice, amount) VALUES(?,?,?,?)", (uid, r.prediction_id, r.choice, r.amount))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "message": "Ставка принята!"}

@app.post("/get_clan_chest")
def get_clan_chest(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    member = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if not member: raise HTTPException(400, "Не в клане")
    clan_id = member[0]
    row = conn.execute("SELECT current_amount, goal_amount FROM clan_chest WHERE clan_id=?", (clan_id,)).fetchone()
    if not row:
        conn.execute("INSERT INTO clan_chest(clan_id) VALUES(?)", (clan_id,))
        conn.commit()
        current, goal = 0, 100000000
    else: current, goal = row[0], row[1]
    donors = conn.execute("SELECT u.uid, u.avatar, COALESCE(SUM(ch.amount), 0) as total FROM users u JOIN clan_chest_history ch ON u.uid = ch.uid WHERE ch.clan_id = ? GROUP BY u.uid ORDER BY total DESC LIMIT 5", (clan_id,)).fetchall()
    return {"current": current, "goal": goal, "donors": [{"name": f"{str(d[0])[:3]}***{str(d[0])[-2:]}", "avatar": d[1] or '👤', "amount": d[2]} for d in donors]}

@app.post("/donate_clan")
def donate_clan(r: DonateClanReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    conn = db()
    member = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if not member: raise HTTPException(400, "Не в клане")
    clan_id = member[0]
    if r.amount < 1000: raise HTTPException(400, "Минимум 1000")
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (r.amount, uid, r.amount))
    if cur.rowcount == 0: raise HTTPException(400, "Мало фишек")
    row = conn.execute("SELECT current_amount, goal_amount FROM clan_chest WHERE clan_id=?", (clan_id,)).fetchone()
    if not row:
        conn.execute("INSERT INTO clan_chest(clan_id, current_amount) VALUES(?, ?)", (clan_id, r.amount))
        current, goal = r.amount, 100000000
    else:
        current, goal = row[0] + r.amount, row[1]
        conn.execute("UPDATE clan_chest SET current_amount = ? WHERE clan_id=?", (current, clan_id))
    conn.execute("INSERT INTO clan_chest_history(clan_id, uid, amount, timestamp) VALUES(?,?,?,?)", (clan_id, uid, r.amount, int(time.time())))
    conn.commit()
    if current >= goal:
        members = conn.execute("SELECT uid FROM clan_members WHERE clan_id=?", (clan_id,)).fetchall()
        for m in members: conn.execute("UPDATE users SET balance = balance + 5000000 WHERE uid=?", (m[0],))
        conn.execute("UPDATE clan_chest SET current_amount = 0 WHERE clan_id=?", (clan_id,))
        conn.commit()
        return {"status": "ok", "balance": get_user(uid)["balance"], "current": 0, "message": "🎉 ЦЕЛЬ! Все получили по 5 млн!"}
    return {"status": "ok", "balance": get_user(uid)["balance"], "current": current, "message": f"Внесено {r.amount:,} фишек"}

@app.on_event("shutdown")
def shutdown_db():
    global _db_conn
    if _db_conn is not None:
        try: _db_conn.close()
        except Exception: pass
        _db_conn = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def index():
    return FileResponse("index.html")
    
