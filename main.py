import hmac, hashlib, json, random, time, sqlite3, os, threading
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
        conn.execute("INSERT INTO users(uid, balance, energy, last_energy_time) VALUES(?, 5000, 1000, ?)", (uid, int(time.time())))
        conn.commit()
        row = (5000, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '👤', 0, 0, 0, 1000, 1, 'default', 'default', int(time.time()))
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
class Req(BaseModel): init_data: str
class RefReq(BaseModel): init_data: str; referrer_id: int
class SpinReq(BaseModel): init_data: str; bet: int; game: str; bonus_buy: bool = False; free_spins: int = 0
class RoulBetReq(BaseModel): init_data: str; bets: list
class BuyAssetReq(BaseModel): init_data: str; item_id: str
class ExchangeReq(BaseModel): init_data: str; currency: str; amount: int; action: str
class BuyAvatarReq(BaseModel): init_data: str; avatar_id: str
class ClaimQuestReq(BaseModel): init_data: str; quest_id: str
class CreateClanReq(BaseModel): init_data: str; name: str
class JoinClanReq(BaseModel): init_data: str; clan_id: int
class PromoReq(BaseModel): init_data: str; code: str
class CryptoReq(BaseModel): init_data: str; amount: float; action: str
class BlackMarketReq(BaseModel): init_data: str; item_id: int
class ChatSendReq(BaseModel): init_data: str; text: str; is_clan: bool = False
class ChatGetReq(BaseModel): init_data: str; is_clan: bool = False; last_id: int = 0
class BuyVipReq(BaseModel): init_data: str
class HouseReq(BaseModel): init_data: str
class ClaimPrizeReq(BaseModel): init_data: str; prize_type: str; prize_value: int
class TapReq(BaseModel): init_data: str; taps: int
class UpgradePickReq(BaseModel): init_data: str
class DonateReq(BaseModel): init_data: str; item_id: str
class CheckPayReq(BaseModel): init_data: str; item_id: str
class TechReq(BaseModel): init_data: str; node_id: str
class StoryClaimReq(BaseModel): init_data: str; chapter_id: int
class PredBetReq(BaseModel): init_data: str; prediction_id: int; choice: str; amount: int
class DonateClanReq(BaseModel): init_data: str; amount: int
class SellAssetReq(BaseModel): init_data: str; asset_id: int; price: int

@app.post("/state")
def state(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    today = int(time.strftime("%j"))
    if d["wheel_day"] != today:
        set_user(uid, wheel_daily=0, wheel_day=today); d["wheel_daily"] = 0
    if d["is_spinning"] == 1:
        set_user(uid, is_spinning=0); d["is_spinning"] = 0
        
    conn = db()
    market = conn.execute("SELECT price, last_update FROM crypto_market WHERE id=1").fetchone()
    if now - market[1] > 1800:
        change = random.uniform(-0.2, 0.3)
        new_price = max(10.0, market[0] * (1 + change))
        conn.execute("UPDATE crypto_market SET price=?, last_update=? WHERE id=1", (new_price, now))
        conn.commit()
    conn.execute("DELETE FROM black_market WHERE expires_at < ?", (now,))
    conn.execute("DELETE FROM active_events WHERE expires_at < ?", (now,))
    
    active_war = conn.execute("SELECT id FROM clan_wars WHERE status='active'").fetchone()
    if not active_war:
        clans = conn.execute("SELECT id FROM clans ORDER BY RANDOM() LIMIT 2").fetchall()
        if len(clans) == 2:
            conn.execute("INSERT INTO clan_wars(clan1_id, clan2_id, start_time, end_time) VALUES(?,?,?,?)", 
                          (clans[0][0], clans[1][0], now, now + 604800))
            conn.commit()
    conn.execute("UPDATE clan_wars SET status='finished' WHERE status='active' AND end_time < ?", (now,))
    conn.commit()

    event_row = conn.execute("SELECT event_type, multiplier, expires_at FROM active_events LIMIT 1").fetchone()
    event_data = {"type": event_row[0], "multiplier": event_row[1], "time_left": event_row[2] - now} if event_row else None
    
    house_row = conn.execute("SELECT level FROM player_house WHERE uid=?", (uid,)).fetchone()
    house_level = house_row[0] if house_row else 0
    
    member = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    clan_id = member[0] if member else 0

    can_wheel = (d["wheel_daily"] < 5) and (now >= d["wheel_time"])
    time_left = max(0, d["wheel_time"] - now)
    return {"balance": int(d["balance"]), "wheel_ready": can_wheel, "wheel_time_left": time_left, "wheel_daily": d["wheel_daily"], "ad_ready": now - d["last_ad"] > 60, "ad_allowed": True, "free_spins": d["free_spins"], "level": d["level"], "xp": d["xp"], "next_level_xp": d["level"] * 15000, "ref_count": d["ref_count"], "fish_caught": d["fish_caught"], "total_wilds": d["total_wilds"], "usd": d["usd"], "eur": d["eur"], "aed": d["aed"], "daily_streak": d["daily_streak"], "last_daily": d["last_daily"], "avatar": d["avatar"], "vip_expires": d["vip_expires"], "active_event": event_data, "house_level": house_level, "clan_id": clan_id, "active_skin": d["active_skin"], "active_frame": d["active_frame"]}

@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data); uid = u["id"]
    if r.game not in GAMES: raise HTTPException(400, "Неизвестная игра")
    conn = db()
    d = get_user(uid)
    game_conf = GAMES[r.game]
    is_fs = d["free_spins"] > 0
    
    if not r.free_spins and not r.bonus_buy and d["free_spins"] > 0:
        set_user(uid, free_spins=0, fish_caught=0, total_wilds=0)
        d = get_user(uid); is_fs = False
        
    actual_bet = d["fs_bet"] if is_fs else (r.bet * 150 if r.bonus_buy else r.bet)
    cost = 0 if is_fs else actual_bet
    if not is_fs and r.bet < game_conf["min_bet"]: raise HTTPException(400, f"Мин. ставка {game_conf['min_bet']}")
    if not is_fs and r.bet > 5000: raise HTTPException(400, "Максимальная ставка — 5000")
    if not is_fs and cost < 0: raise HTTPException(400, "Некорректная ставка")
    
    if not is_fs:
        cur = conn.execute(
            "UPDATE users SET balance = balance - ?, is_spinning = 1 WHERE uid=? AND balance >= ? AND is_spinning = 0",
            (cost, uid, cost)
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(400, "Недостаточно фишек или спин уже идёт")
        conn.commit()
    else:
        set_user(uid, is_spinning=1)
    
    bal = d["balance"] - cost
    
    is_first_fs = is_fs and d["free_spins"] in [10, 15, 20]
    grid, fish_prices = generate_grid(r.game, is_fs or r.bonus_buy, d["total_wilds"], is_first_fs)
    scatters = 0
    
    if r.bonus_buy:
        for col_idx in range(len(grid)):
            for row_idx in range(len(grid[col_idx])):
                if grid[col_idx][row_idx] == game_conf.get("scatter"): grid[col_idx][row_idx] = 0
        grid[1][0] = game_conf["scatter"]; grid[3][1] = game_conf["scatter"]; grid[2][2] = game_conf["scatter"]; scatters = 3
        if r.game == "fishing":
            grid[2][1] = game_conf["wild"]; grid[1][1] = game_conf["fish_cash"][0]; grid[3][1] = game_conf["fish_cash"][1]; grid[2][0] = game_conf["fish_cash"][2]
            fish_prices[(1,1)] = 10; fish_prices[(3,1)] = 20; fish_prices[(2,0)] = 5
    else:
        if not is_fs and game_conf.get("scatter") is not None:
            for col in grid:
                for sym in col:
                    if sym == game_conf["scatter"]: scatters += 1
        elif is_fs:
             for col_idx in range(len(grid)):
                for row_idx in range(len(grid[col_idx])):
                    if grid[col_idx][row_idx] == game_conf.get("scatter"): grid[col_idx][row_idx] = 0
                 
    win_amount, win_lines, scatters_nat, fish_data, wilds_count = check_win(grid, r.game, actual_bet, fish_prices, d["fish_caught"], d["total_wilds"])
    if not r.bonus_buy and not is_fs: scatters = scatters_nat
    
    now_ev = int(time.time())
    ev = conn.execute("SELECT event_type, multiplier FROM active_events WHERE expires_at > ?", (now_ev,)).fetchone()
    if ev and ev[0] in ["all_slots", "gold_rush"]:
        win_amount = int(win_amount * ev[1])
    
    if d["vip_expires"] > now_ev:
        win_amount = int(win_amount * 1.1)
    
    new_free_spins = d["free_spins"]; new_fish_caught = d["fish_caught"]; new_fs_bet = d["fs_bet"]; new_total_wilds = d["total_wilds"]
    
    if is_fs:
        new_free_spins -= 1
        if wilds_count > 0:
            old_wilds = new_total_wilds
            new_total_wilds += wilds_count
            if (new_total_wilds // 4) > (old_wilds // 4):
                new_free_spins = 10 
                if new_total_wilds > 12: new_total_wilds = 12
        if new_free_spins <= 0: 
            new_fs_bet = 0; new_fish_caught = 0; new_total_wilds = 0
    elif scatters >= 3:
        if scatters == 3: new_free_spins = 10
        elif scatters == 4: new_free_spins = 15
        elif scatters >= 5: new_free_spins = 20
        new_fish_caught = 0; new_total_wilds = 0; new_fs_bet = r.bet
        
    bal += win_amount
    new_xp = d["xp"] + win_amount 
    new_level = d["level"]; next_level_xp = new_level * 15000
    if new_xp >= next_level_xp: new_level += 1; bal += 5000; new_xp -= next_level_xp

    jackpot_contrib = int(cost * 0.05)
    conn.execute("UPDATE global_jackpot SET amount = amount + ? WHERE id=1", (jackpot_contrib,))
    jackpot_won = 0
    if r.game == "fruits":
        count_7 = sum(1 for col in grid for sym in col if sym == 5)
        if count_7 >= 3:
            jp_amount = conn.execute("SELECT amount FROM global_jackpot WHERE id=1").fetchone()[0]
            jackpot_won = jp_amount; bal += jp_amount; win_amount += jp_amount
            conn.execute("UPDATE global_jackpot SET amount = 1000000 WHERE id=1")
    elif r.game == "fishing" and scatters >= 5:
        jp_amount = conn.execute("SELECT amount FROM global_jackpot WHERE id=1").fetchone()[0]
        jackpot_won = jp_amount; bal += jp_amount; win_amount += jp_amount
        conn.execute("UPDATE global_jackpot SET amount = 1000000 WHERE id=1")
    conn.commit()

    set_user(uid, balance=bal, free_spins=new_free_spins, fs_bet=new_fs_bet, xp=new_xp, level=new_level, is_spinning=0, fish_caught=new_fish_caught, total_wilds=new_total_wilds)

    if win_amount > 0 and d["referrer_id"] != 0:
        ref_user = conn.execute("SELECT balance, ref_earnings FROM users WHERE uid=?", (d["referrer_id"],)).fetchone()
        if ref_user:
            ref_rate = 0.03 + get_tech_bonus(d["referrer_id"], "social_ref")
            ref_bonus = int(win_amount * ref_rate)
            conn.execute("UPDATE users SET balance=balance+?, ref_earnings=ref_earnings+? WHERE uid=?", (ref_bonus, ref_bonus, d["referrer_id"]))
            conn.commit()

    row_q = conn.execute("SELECT spins_count, win_sum, last_reset FROM quests WHERE uid=?", (uid,)).fetchone()
    if not row_q:
        conn.execute("INSERT INTO quests(uid, spins_count, win_sum, last_reset) VALUES(?, 1, ?, ?)", (uid, win_amount, now_ev))
    else:
        if now_ev - row_q[2] > 86400: conn.execute("UPDATE quests SET spins_count=1, win_sum=?, last_reset=? WHERE uid=?", (win_amount, now_ev, uid))
        else: conn.execute("UPDATE quests SET spins_count=spins_count+1, win_sum=win_sum+? WHERE uid=?", (win_amount, uid))
    conn.commit()
    
    if win_amount > 0:
        conn.execute("INSERT INTO tournament(uid, score) VALUES(?, ?) ON CONFLICT(uid) DO UPDATE SET score = score + ?", (uid, win_amount, win_amount))
        conn.commit()
    
    member = conn.execute("SELECT clan_id FROM clan_members WHERE uid=?", (uid,)).fetchone()
    if member and win_amount > 0:
        clan_bonus_rate = 1.0 + get_tech_bonus(uid, "social_clan")
        clan_score = int(win_amount * clan_bonus_rate)
        conn.execute("UPDATE clans SET total_score = total_score + ? WHERE id=?", (clan_score, member[0]))
        war = conn.execute("SELECT id, clan1_id, clan2_id FROM clan_wars WHERE status='active'").fetchone()
        if war:
            if member[0] == war[1]: conn.execute("UPDATE clan_wars SET clan1_score = clan1_score + ? WHERE id=?", (clan_score, war[0]))
            elif member[0] == war[2]: conn.execute("UPDATE clan_wars SET clan2_score = clan2_score + ? WHERE id=?", (clan_score, war[0]))
        conn.commit()
    
    ui_mult = 1
    if new_total_wilds >= 12: ui_mult = 10
    elif new_total_wilds >= 8: ui_mult = 5
    elif new_total_wilds >= 4: ui_mult = 2
    
    return {"grid": grid, "win": win_amount, "balance": bal, "lines": win_lines, "scatters": scatters, "bonus_mult": ui_mult, "fish_data": fish_data, "is_free_spin": is_fs, "free_spins_left": new_free_spins, "fish_caught": new_fish_caught, "level": new_level, "xp": new_xp, "wilds_count": wilds_count, "total_wilds": new_total_wilds, "jackpot_won": jackpot_won}

@app.post("/reset_fs")
def reset_fs(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT free_spins FROM users WHERE uid=?", (uid,)).fetchone()
    if row and row[0] > 0:
        return {"status": "kept", "free_spins": row[0]}
    set_user(uid, free_spins=0, fs_bet=0, fish_caught=0, total_wilds=0)
    return {"status": "ok"}

@app.post("/roulette/bet")
def roul_bet(r: RoulBetReq):
    u = verify(r.init_data); uid = u["id"]; now = int(time.time())
    total_bet = sum(b['amount'] for b in r.bets)
    if total_bet <= 0: raise HTTPException(400, "Ставка не может быть 0")
    if total_bet > 5000: raise HTTPException(400, "Максимальная общая ставка — 5000")
    conn = db()
    one_hour_ago = now - 3600
    conn.execute("DELETE FROM roulette_history WHERE timestamp < ?", (now - 86400,))
    total_last_hour = conn.execute("SELECT SUM(amount) FROM roulette_history WHERE uid=? AND timestamp > ?", (uid, one_hour_ago)).fetchone()[0] or 0
    if total_last_hour + total_bet > 100000:
        raise HTTPException(400, f"Лимит 100000 в час.")
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (total_bet, uid, total_bet))
    if cur.rowcount == 0:
        conn.rollback()
        raise HTTPException(400, "Мало фишек")
    conn.execute("INSERT INTO roulette_history(uid, amount, timestamp) VALUES(?,?,?)", (uid, total_bet, now))
    conn.execute("DELETE FROM roulette_bets WHERE uid=?", (uid,))
    for b in r.bets: conn.execute("INSERT INTO roulette_bets(uid, bet_type, bet_value, amount) VALUES (?,?,?,?)", (uid, b['type'], b['value'], b['amount']))
    conn.commit()
    new_balance = get_user(uid)["balance"]
    return {"status": "ok", "balance": new_balance}

@app.post("/roulette/spin")
def roul_spin(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    conn = db(); bets = conn.execute("SELECT bet_type, bet_value, amount FROM roulette_bets WHERE uid=?", (uid,)).fetchall()
    if not bets: raise HTTPException(400, "Нет ставок")
    conn.execute("DELETE FROM roulette_bets WHERE uid=?", (uid,)); conn.commit()
    win_num = int(random.randint(0, 36))
    is_red = win_num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    is_black = win_num != 0 and not is_red
    total_win = 0
    for b_type, b_val, amount in bets:
        amount = int(amount)
        if b_type == 'number':
            if int(b_val) == win_num: total_win += amount * (10 if win_num == 0 else 36)
        elif b_type == 'color':
            if b_val == 'red' and is_red: total_win += amount * 2
            if b_val == 'black' and is_black: total_win += amount * 2
        elif b_type == 'parity':
            if b_val == 'even' and win_num != 0 and win_num % 2 == 0: total_win += amount * 2
            if b_val == 'odd' and win_num % 2 != 0: total_win += amount * 2
        elif b_type == 'half':
            if b_val == 'low' and 1 <= win_num <= 18: total_win += amount * 3
            if b_val == 'high' and 19 <= win_num <= 36: total_win += amount * 3
    now_ev = int(time.time())
    ev = conn.execute("SELECT event_type, multiplier FROM active_events WHERE expires_at > ?", (now_ev,)).fetchone()
    if ev and ev[0] in ["all_games", "roulette_boost"]:
        total_win = int(total_win * ev[1])
    if d["vip_expires"] > now_ev:
        total_win = int(total_win * 1.1)
    tech_bonus = get_tech_bonus(uid, "lucky_roulette")
    if tech_bonus > 0:
        total_win = int(total_win * (1 + tech_bonus))
    new_balance = int(d["balance"] + total_win)
    set_user(uid, balance=new_balance)
    return {"win_num": win_num, "win_amount": int(total_win), "balance": new_balance}

@app.post("/referral")
def referral(r: RefReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if uid == r.referrer_id or d["referrer_id"] != 0: return {"status": "error"}
    conn = db(); ref_row = conn.execute("SELECT uid FROM users WHERE uid=?", (r.referrer_id,)).fetchone()
    if not ref_row: return {"status": "error"}
    conn.execute("UPDATE users SET referrer_id=?, balance=balance+1000 WHERE uid=?", (r.referrer_id, uid))
    conn.execute("UPDATE users SET ref_count=ref_count+1, balance=balance+2000 WHERE uid=?", (r.referrer_id,))
    conn.commit()
    return {"status": "success"}

@app.post("/ref_stats")
def ref_stats(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    user = conn.execute("SELECT ref_count, ref_earnings FROM users WHERE uid=?", (uid,)).fetchone()
    friends = conn.execute("SELECT uid, avatar FROM users WHERE referrer_id=? LIMIT 20", (uid,)).fetchall()
    friends_list = [{"id": f"{str(f[0])[:3]}***{str(f[0])[-2:]}", "avatar": f[1] or '👤'} for f in friends]
    return {"ref_count": user[0] if user else 0, "ref_earnings": user[1] if user else 0, "friends": friends_list}

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

@app.post("/buy_vip")
def buy_vip(r: BuyVipReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    VIP_COST_USD = 100; VIP_DURATION = 30 * 86400
    if d["usd"] < VIP_COST_USD: raise HTTPException(400, f"Нужно {VIP_COST_USD} USD")
    current_expire = d["vip_expires"] if d["vip_expires"] > now else now
    new_expire = current_expire + VIP_DURATION
    conn = db()
    cur = conn.execute("UPDATE users SET usd = usd - ?, vip_expires=? WHERE uid=? AND usd >= ?", (VIP_COST_USD, new_expire, uid, VIP_COST_USD))
    if cur.rowcount == 0: raise HTTPException(400, "Мало USD")
    conn.commit()
    d = get_user(uid)
    return {"status": "ok", "usd": d["usd"], "vip_expires": new_expire, "message": "Добро пожаловать в VIP-клуб!"}

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

# --- СКИНЫ ---
@app.post("/get_skins")
def get_skins(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    owned_rows = conn.execute("SELECT skin_id FROM user_skins WHERE uid=?", (uid,)).fetchall()
    owned = [row[0] for row in owned_rows]
    if 'default' not in owned: owned.append('default')
    result = []
    for key, data in SKINS_CATALOG.items():
        result.append({"id": key, "name": data["name"], "price": data["price"], "is_owned": key in owned})
    return {"skins": result}

@app.post("/buy_skin")
def buy_skin(r: BuyAvatarReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    skin = SKINS_CATALOG.get(r.avatar_id)
    if not skin: raise HTTPException(400, "Скин не найден")
    conn = db()
    owned = conn.execute("SELECT 1 FROM user_skins WHERE uid=? AND skin_id=?", (uid, r.avatar_id)).fetchone()
    if not owned and skin["price"] > 0:
        cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (skin["price"], uid, skin["price"]))
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(400, "Недостаточно фишек")
        conn.execute("INSERT INTO user_skins(uid, skin_id) VALUES(?, ?)", (uid, r.avatar_id))
    conn.execute("UPDATE users SET active_skin=? WHERE uid=?", (r.avatar_id, uid))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "active_skin": r.avatar_id, "message": f"Скин '{skin['name']}' активирован!"}

# --- АУКЦИОН ---
@app.post("/auction/list")
def auction_list(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    rows = conn.execute("""
        SELECT a.id, a.seller_id, u.avatar, a.item_id, a.price, a.created_at 
        FROM auction a JOIN users u ON a.seller_id = u.uid 
        WHERE a.seller_id != ? ORDER BY a.created_at DESC
    """, (uid,)).fetchall()
    lots = []
    for row in rows:
        item_data = ASSETS_CATALOG.get(row[3], {"name": "Неизвестно", "emoji": "❓"})
        lots.append({"id": row[0], "seller": f"{str(row[1])[:3]}***{str(row[1])[-2:]}", "seller_avatar": row[2] or '👤', "item_id": row[3], "name": item_data["name"], "emoji": item_data["emoji"], "price": row[4], "time": row[5]})
    return {"lots": lots}

@app.post("/auction/my")
def auction_my(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    rows = conn.execute("SELECT id, item_id, price, created_at FROM auction WHERE seller_id=? ORDER BY created_at DESC", (uid,)).fetchall()
    lots = []
    for row in rows:
        item_data = ASSETS_CATALOG.get(row[1], {"name": "Неизвестно", "emoji": "❓"})
        lots.append({"id": row[0], "item_id": row[1], "name": item_data["name"], "emoji": item_data["emoji"], "price": row[2], "time": row[3]})
    return {"lots": lots}

@app.post("/auction/sell")
def auction_sell(r: SellAssetReq):
    u = verify(r.init_data); uid = u["id"]
    if r.price < 1000: raise HTTPException(400, "Минимальная цена 1000 фишек")
    conn = db()
    asset = conn.execute("SELECT item_id FROM assets WHERE id=? AND uid=?", (r.asset_id, uid)).fetchone()
    if not asset: raise HTTPException(400, "Имущество не найдено")
    item_id = asset[0]
    conn.execute("DELETE FROM assets WHERE id=? AND uid=?", (r.asset_id, uid))
    conn.execute("INSERT INTO auction(seller_id, asset_id, item_id, price, created_at) VALUES(?, ?, ?, ?, ?)", (uid, r.asset_id, item_id, r.price, int(time.time())))
    conn.commit()
    return {"status": "ok", "message": "Лот выставлен на аукцион!"}

@app.post("/auction/cancel")
def auction_cancel(r: BlackMarketReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    lot = conn.execute("SELECT item_id, asset_id FROM auction WHERE id=? AND seller_id=?", (r.item_id, uid)).fetchone()
    if not lot: raise HTTPException(400, "Лот не найден или это не ваш лот")
    item_id, original_asset_id = lot
    conn.execute("INSERT INTO assets(id, uid, item_id, buy_price, buy_time) VALUES(?, ?, ?, ?, ?)", (original_asset_id, uid, item_id, ASSETS_CATALOG[item_id]["price"], int(time.time())))
    conn.execute("DELETE FROM auction WHERE id=?", (r.item_id,))
    conn.commit()
    return {"status": "ok", "message": "Лот снят, имущество возвращено."}

@app.post("/auction/buy")
def auction_buy(r: BlackMarketReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    conn = db()
    lot = conn.execute("SELECT seller_id, item_id, price FROM auction WHERE id=?", (r.item_id,)).fetchone()
    if not lot: raise HTTPException(400, "Лот не найден или уже продан")
    if lot[0] == uid: raise HTTPException(400, "Нельзя купить свой лот")
    if d["balance"] < lot[2]: raise HTTPException(400, "Недостаточно фишек")
    cur = conn.execute("UPDATE users SET balance = balance - ? WHERE uid=? AND balance >= ?", (lot[2], uid, lot[2]))
    if cur.rowcount == 0: raise HTTPException(400, "Ошибка списания")
    seller_income = int(lot[2] * 0.95)
    conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (seller_income, lot[0]))
    conn.execute("DELETE FROM auction WHERE id=?", (r.item_id,))
    conn.execute("INSERT INTO assets(uid, item_id, buy_price, buy_time) VALUES(?, ?, ?, ?)", (uid, lot[1], lot[2], int(time.time())))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"], "message": f"Вы купили {ASSETS_CATALOG[lot[1]]['name']}!"}

# --- КВЕСТЫ ---
@app.post("/get_quests")
def get_quests(r: Req):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    row = conn.execute("SELECT spins_count, win_sum, last_reset, taps_count, mine_earned, pickaxe_upgrades FROM quests WHERE uid=?", (uid,)).fetchone()
    now = int(time.time()); today = now // 86400
    if not row or (now - row[2] > 86400):
        if not row: conn.execute("INSERT INTO quests(uid, spins_count, win_sum, last_reset, taps_count, mine_earned, pickaxe_upgrades) VALUES(?, 0, 0, ?, 0, 0, 0)", (uid, now))
        else: conn.execute("UPDATE quests SET spins_count=0, win_sum=0, last_reset=?, taps_count=0, mine_earned=0, pickaxe_upgrades=0 WHERE uid=?", (now, uid))
        conn.commit(); spins, wins, taps, mined, upgrades = 0, 0, 0, 0, 0
    else:
        spins, wins, taps, mined, upgrades = row[0], row[1], row[3], row[4], row[5]
    claimed = set(x[0] for x in conn.execute("SELECT quest_id FROM claimed_quests WHERE uid=? AND day=?", (uid, today)).fetchall())
    all_quests = [
        {"id": "spins_10", "text": "Сделай 10 спинов", "target": 10, "progress": spins, "reward": 5000},
        {"id": "spins_50", "text": "Сделай 50 спинов", "target": 50, "progress": spins, "reward": 25000},
        {"id": "win_100k", "text": "Выиграй 100 000 фишек", "target": 100000, "progress": wins, "reward": 50000},
        {"id": "taps_500", "text": "Сделай 500 тапов в шахте", "target": 500, "progress": taps, "reward": 10000},
        {"id": "mined_50k", "text": "Добудь 50 000 фишек в шахте", "target": 50000, "progress": mined, "reward": 25000},
        {"id": "upgrade_1", "text": "Улучши кирку 1 раз", "target": 1, "progress": upgrades, "reward": 50000}
    ]
    for q in all_quests: q["is_claimed"] = q["id"] in claimed
    return {"quests": all_quests}

@app.post("/claim_quest")
def claim_quest(r: ClaimQuestReq):
    u = verify(r.init_data); uid = u["id"]
    conn = db()
    now = int(time.time()); today = now // 86400
    row = conn.execute("SELECT spins_count, win_sum, taps_count, mine_earned, pickaxe_upgrades FROM quests WHERE uid=?", (uid,)).fetchone()
    if not row: raise HTTPException(400, "Ошибка")
    spins, wins, taps, mined, upgrades = row[0], row[1], row[2], row[3], row[4]
    rewards = {"spins_10": 5000, "spins_50": 25000, "win_100k": 50000, "taps_500": 10000, "mined_50k": 25000, "upgrade_1": 50000}
    targets = {"spins_10": 10, "spins_50": 50, "win_100k": 100000, "taps_500": 500, "mined_50k": 50000, "upgrade_1": 1}
    if r.quest_id not in rewards: raise HTTPException(400, "Неизвестный квест")
    already = conn.execute("SELECT 1 FROM claimed_quests WHERE uid=? AND quest_id=? AND day=?", (uid, r.quest_id, today)).fetchone()
    if already: raise HTTPException(400, "Награда уже получена")
    progress = 0
    if r.quest_id.startswith("spins"): progress = spins
    elif r.quest_id.startswith("win"): progress = wins
    elif r.quest_id.startswith("taps"): progress = taps
    elif r.quest_id.startswith("mined"): progress = mined
    elif r.quest_id.startswith("upgrade"): progress = upgrades
    if progress < targets[r.quest_id]: raise HTTPException(400, "Не выполнен")
    reward = rewards[r.quest_id]
    conn.execute("UPDATE users SET balance = balance + ? WHERE uid=?", (reward, uid))
    conn.execute("INSERT OR IGNORE INTO claimed_quests(uid, quest_id, day) VALUES(?, ?, ?)", (uid, r.quest_id, today))
    conn.commit()
    return {"status": "ok", "balance": get_user(uid)["balance"]}

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
