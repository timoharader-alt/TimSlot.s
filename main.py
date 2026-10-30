import hmac, hashlib, json, random, time, sqlite3, os
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
app = FastAPI()

def db():
    c = sqlite3.connect("slot.db")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        uid INTEGER PRIMARY KEY, balance INTEGER DEFAULT 5000, 
        wheel_time INTEGER DEFAULT 0, wheel_daily INTEGER DEFAULT 0, wheel_day INTEGER DEFAULT 0, 
        free_spins INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        referrer_id INTEGER DEFAULT 0, ref_count INTEGER DEFAULT 0,
        is_spinning INTEGER DEFAULT 0, fs_bet INTEGER DEFAULT 0, last_ad INTEGER DEFAULT 0,
        fish_caught INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS roulette_bets(
        uid INTEGER, bet_type TEXT, bet_value TEXT, amount INTEGER
    )""")
    return c

def get_user(uid):
    c = db()
    row = c.execute("SELECT balance, wheel_time, wheel_daily, wheel_day, free_spins, xp, level, referrer_id, ref_count, fs_bet, last_ad, is_spinning, fish_caught FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        c.execute("INSERT INTO users(uid, balance) VALUES(?, 5000)", (uid,))
        c.commit()
        row = (5000, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0)
    c.close()
    return {"balance": row[0], "wheel_time": row[1], "wheel_daily": row[2], "wheel_day": row[3], "free_spins": row[4], "xp": row[5], "level": row[6], "referrer_id": row[7], "ref_count": row[8], "fs_bet": row[9], "last_ad": row[10], "is_spinning": row[11], "fish_caught": row[12]}

def set_user(uid, **kw):
    c = db()
    for k, v in kw.items(): c.execute(f"UPDATE users SET {k}=? WHERE uid=?", (v, uid))
    c.commit(); c.close()

def verify(init_data: str) -> dict:
    if not BOT_TOKEN: raise HTTPException(500, "BOT_TOKEN не задан")
    try: p = dict(parse_qsl(init_data, strict_parsing=True))
    except: raise HTTPException(400, "bad init_data")
    h = p.pop("hash", None)
    if not h: raise HTTPException(400, "no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), h):
        raise HTTPException(401, "bad signature")
    return json.loads(p["user"])

GAMES = {
    "fruits": {"cols": 3, "rows": 1, "min_bet": 10, "symbols": [{"id":0, "pay":[0, 10, 30]}, {"id":1, "pay":[0, 15, 50]}, {"id":2, "pay":[0, 20, 100]}, {"id":3, "pay":[0, 50, 200]}, {"id":4, "pay":[0, 100, 500]}, {"id":5, "pay":[0, 200, 1000]}], "scatter": None},
    "fishing": {"cols": 5, "rows": 3, "min_bet": 10, "symbols": [{"id":0, "pay":[5, 25, 100]}, {"id":1, "pay":[5, 25, 100]}, {"id":2, "pay":[5, 25, 100]}, {"id":3, "pay":[5, 25, 100]}, {"id":4, "pay":[5, 25, 100]}, {"id":5, "pay":[10, 50, 200]}, {"id":6, "pay":[20, 100, 500]}, {"id":7, "pay":[20, 100, 500]}, {"id":8, "pay":[30, 150, 1000]}, {"id":9, "pay":[50, 200, 2000]}], "scatter": 10, "wild": 11, "fish_cash": [12, 13, 14, 15]}
}

LINES = {
    "fruits": [[0,0,0]],
    "fishing": [[1,1,1,1,1], [0,0,0,0,0], [2,2,2,2,2], [0,1,2,1,0], [2,1,0,1,2], [0,0,1,2,2], [2,2,1,0,0], [0,1,2,2,2], [2,1,0,0,0], [0,0,1,0,0]]
}

def generate_grid(game_key, is_bonus=False):
    g = GAMES[game_key]
    cols, rows = g["cols"], g["rows"]
    grid = [[None]*rows for _ in range(cols)]
    fish_prices = {}
    if game_key == "fishing":
        for c in range(cols):
            for r in range(rows):
                rand = random.random()
                if rand < 0.01: grid[c][r] = g["scatter"]
                elif rand < (0.20 if is_bonus else 0.05): 
                    grid[c][r] = random.choice(g["fish_cash"]); fish_prices[(c, r)] = random.choice([2, 5, 10, 20, 50, 100])
                elif rand < (0.22 if is_bonus else 0.07): grid[c][r] = g["wild"]
                else: grid[c][r] = random.choice(range(10))
        return grid, fish_prices
    weights = [70, 60, 50, 40, 20, 5]
    pool = [s["id"] for s in g["symbols"] for _ in range(weights[s["id"]] if s["id"] < len(weights) else 1)]
    for _ in range(cols):
        col = []
        for _ in range(rows):
            if g["scatter"] is not None and random.random() < 0.02: col.append(g["scatter"])
            else: col.append(random.choice(pool))
        grid[_] = col
    return grid, fish_prices

def check_win(grid, game_key, bet, fish_prices, fish_caught=0):
    g = GAMES[game_key]; lines = LINES[game_key]; total_win = 0; win_lines = []; scatters = 0; wilds_count = 0; fish_data = []
    if g.get("scatter") is not None:
        for col in grid:
            for sym in col:
                if sym == g["scatter"]: scatters += 1
    if game_key == "fishing":
        wild_coords = [(c, r) for c in range(len(grid)) for r in range(len(grid[c])) if grid[c][r] == g["wild"]]
        wilds_count = len(wild_coords)
        if wilds_count >= 1:
            # Логика множителя изменена в spin()
            mult = 1
            if fish_caught >= 20: mult = 10
            elif fish_caught >= 12: mult = 5
            elif fish_caught >= 8: mult = 3
            elif fish_caught >= 4: mult = 2
            for c in range(len(grid)):
                for r in range(len(grid[c])):
                    if grid[c][r] in g["fish_cash"]:
                        price_mult = fish_prices.get((c, r), random.choice([2, 5, 10, 20, 50, 100]))
                        val = price_mult * bet
                        total_win += val * mult
                        fish_data.append({"col": c, "row": r, "val": val, "mult": mult})
    for line_idx, line in enumerate(lines):
        first_sym = grid[0][line[0]]
        if first_sym is None or first_sym >= 10: continue
        count = 1
        for col in range(1, len(grid)):
            sym = grid[col][line[col]]
            if sym == first_sym or (game_key == "fishing" and sym == g["wild"]): count += 1
            elif first_sym == g.get("wild") and game_key == "fishing": 
                first_sym = sym; count += 1
            else: break
        min_match = 2 if game_key == "fruits" else 3
        if count >= min_match:
            if game_key == "fishing":
                sym_data = g["symbols"][first_sym] if first_sym < 10 else g["symbols"][0]
                mult = sym_data["pay"][count-3] if count >= 3 else 0
            else:
                sym_data = next(s for s in g["symbols"] if s["id"] == first_sym)
                idx = count - min_match
                mult = sym_data["pay"][idx] if idx < len(sym_data["pay"]) else sym_data["pay"][-1]
            payout = bet * mult
            total_win += payout
            win_lines.append({"line": line_idx, "count": count, "win": payout})
    return total_win, win_lines, scatters, fish_data, wilds_count

class Req(BaseModel): init_data: str
class RefReq(BaseModel): init_data: str; referrer_id: int
class SpinReq(BaseModel): init_data: str; bet: int; game: str; bonus_buy: bool = False; free_spins: int = 0
class RoulBetReq(BaseModel): init_data: str; bets: list

@app.post("/state")
def state(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    today = int(time.strftime("%j"))
    if d["wheel_day"] != today:
        set_user(uid, wheel_daily=0, wheel_day=today); d["wheel_daily"] = 0
    if d["is_spinning"] == 1:
        set_user(uid, is_spinning=0); d["is_spinning"] = 0
    can_wheel = (d["wheel_daily"] < 5) and (now >= d["wheel_time"])
    time_left = max(0, d["wheel_time"] - now)
    return {"balance": d["balance"], "wheel_ready": can_wheel, "wheel_time_left": time_left, "wheel_daily": d["wheel_daily"], "ad_ready": now - d["last_ad"] > 60, "ad_allowed": d["balance"] < 5000, "free_spins": d["free_spins"], "level": d["level"], "xp": d["xp"], "next_level_xp": d["level"] * 15000, "ref_count": d["ref_count"], "fish_caught": d["fish_caught"]}

@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if d["is_spinning"] == 1: 
        set_user(uid, is_spinning=0)
        d["is_spinning"] = 0
    game_conf = GAMES[r.game]
    is_fs = d["free_spins"] > 0
    if not r.free_spins and not r.bonus_buy and d["free_spins"] > 0:
        set_user(uid, free_spins=0, fish_caught=0); d["free_spins"] = 0; d["fish_caught"] = 0; is_fs = False
    actual_bet = d["fs_bet"] if is_fs else (r.bet * 15 if r.bonus_buy else r.bet)
    cost = 0 if is_fs else actual_bet
    if not is_fs and r.bet < game_conf["min_bet"]: raise HTTPException(400, f"Мин. ставка {game_conf['min_bet']}")
    if d["balance"] < cost: raise HTTPException(400, "Недостаточно фишек")
    set_user(uid, is_spinning=1)
    bal = d["balance"] - cost
    grid, fish_prices = generate_grid(r.game, is_fs or r.bonus_buy)
    scatters = 0
    if r.bonus_buy:
        for c in range(len(grid)):
            for row in range(len(grid[c])):
                if grid[c][row] == game_conf.get("scatter"): grid[c][row] = 0
        grid[1][0] = game_conf["scatter"]; grid[3][1] = game_conf["scatter"]; grid[2][2] = game_conf["scatter"]; scatters = 3
        if r.game == "fishing":
            grid[2][1] = game_conf["wild"]; grid[1][1] = game_conf["fish_cash"][0]; grid[3][1] = game_conf["fish_cash"][1]; grid[2][0] = game_conf["fish_cash"][2]
            fish_prices[(1,1)] = 10; fish_prices[(3,1)] = 20; fish_prices[(2,0)] = 5
    else:
        if not is_fs and game_conf.get("scatter") is not None:
            for c in grid:
                for sym in c:
                    if sym == game_conf["scatter"]: scatters += 1
        elif is_fs:
             for c in range(len(grid)):
                for row in range(len(grid[c])):
                    if grid[c][row] == game_conf.get("scatter"): grid[c][row] = 0
             if d["free_spins"] == 10 and r.game == "fishing":
                 grid[2][1] = game_conf["wild"]; grid[1][1] = game_conf["fish_cash"][0]; grid[3][1] = game_conf["fish_cash"][1]; fish_prices[(1,1)] = 10; fish_prices[(3,1)] = 20
    win_amount, win_lines, scatters_nat, fish_data, wilds_count = check_win(grid, r.game, actual_bet, fish_prices, d["fish_caught"])
    if not r.bonus_buy and not is_fs: scatters = scatters_nat
    new_free_spins = d["free_spins"]; new_fish_caught = d["fish_caught"]; new_fs_bet = d["fs_bet"]
    
    if is_fs:
        new_free_spins -= 1
        if wilds_count > 0:
            # НОВАЯ ЛОГИКА: +2 рыбки и +2 фриспина за каждого дикого
            new_fish_caught += (wilds_count * 2)
            new_free_spins += (wilds_count * 2)
            if new_free_spins > 30: new_free_spins = 30
        if new_free_spins <= 0: 
            new_fs_bet = 0
            new_fish_caught = 0
    elif scatters >= 3:
        new_free_spins = 10; new_fish_caught = 0; new_fs_bet = r.bet
        
    bal += win_amount
    new_xp = d["xp"] + win_amount 
    new_level = d["level"]; next_level_xp = new_level * 15000
    if new_xp >= next_level_xp: new_level += 1; bal += 5000; new_xp -= next_level_xp
    set_user(uid, balance=bal, free_spins=new_free_spins, fs_bet=new_fs_bet, xp=new_xp, level=new_level, is_spinning=0, fish_caught=new_fish_caught)
    
    ui_mult = 1
    if new_fish_caught >= 20: ui_mult = 10
    elif new_fish_caught >= 12: ui_mult = 5
    elif new_fish_caught >= 8: ui_mult = 3
    elif new_fish_caught >= 4: ui_mult = 2
    
    return {"grid": grid, "win": win_amount, "balance": bal, "lines": win_lines, "scatters": scatters, "bonus_mult": ui_mult, "fish_data": fish_data, "is_free_spin": is_fs, "free_spins_left": new_free_spins, "fish_caught": new_fish_caught, "level": new_level, "xp": new_xp, "wilds_count": wilds_count}

@app.post("/roulette/bet")
def roul_bet(r: RoulBetReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    total_bet = sum(b['amount'] for b in r.bets)
    if d["balance"] < total_bet: raise HTTPException(400, "Мало фишек")
    c = db(); c.execute("DELETE FROM roulette_bets WHERE uid=?", (uid,))
    for b in r.bets: c.execute("INSERT INTO roulette_bets(uid, bet_type, bet_value, amount) VALUES (?,?,?,?)", (uid, b['type'], b['value'], b['amount']))
    c.commit(); c.close()
    # Логика списания баланса перенесена на фронтенд, поэтому здесь не списываем
    return {"status": "ok", "balance": d["balance"]}

@app.post("/roulette/spin")
def roul_spin(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    c = db(); bets = c.execute("SELECT bet_type, bet_value, amount FROM roulette_bets WHERE uid=?", (uid,)).fetchall()
    if not bets: c.close(); raise HTTPException(400, "Нет ставок")
    c.execute("DELETE FROM roulette_bets WHERE uid=?", (uid,)); c.commit(); c.close()
    win_num = random.randint(0, 36)
    is_red = win_num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    is_black = win_num != 0 and not is_red
    total_win = 0
    for b_type, b_val, amount in bets:
        if b_type == 'number' and int(b_val) == win_num: total_win += amount * 36
        elif b_type == 'color':
            if b_val == 'red' and is_red: total_win += amount * 2
            if b_val == 'black' and is_black: total_win += amount * 2
        elif b_type == 'parity':
            if b_val == 'even' and win_num != 0 and win_num % 2 == 0: total_win += amount * 2
            if b_val == 'odd' and win_num % 2 != 0: total_win += amount * 2
        elif b_type == 'half':
            if b_val == 'low' and 1 <= win_num <= 18: total_win += amount * 2
            if b_val == 'high' and 19 <= win_num <= 36: total_win += amount * 2
    set_user(uid, balance=d["balance"] + total_win)
    return {"win_num": win_num, "win_amount": total_win, "balance": d["balance"] + total_win}

@app.post("/referral")
def referral(r: RefReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if uid == r.referrer_id or d["referrer_id"] != 0: return {"status": "error"}
    c = db(); ref_row = c.execute("SELECT uid FROM users WHERE uid=?", (r.referrer_id,)).fetchone()
    if not ref_row: c.close(); return {"status": "error"}
    c.execute("UPDATE users SET referrer_id=?, balance=balance+1000 WHERE uid=?", (r.referrer_id, uid))
    c.execute("UPDATE users SET ref_count=ref_count+1, balance=balance+2000 WHERE uid=?", (r.referrer_id,))
    c.commit(); c.close()
    return {"status": "success"}

@app.post("/bonus")
def bonus(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if d["wheel_daily"] >= 5: raise HTTPException(400, "Лимит 5 круток")
    if now < d["wheel_time"]: raise HTTPException(400, "Кулдаун 1 час")
    rnd = random.random() * 100
    if rnd < 1: amount = 1000
    elif rnd < 4: amount = 500
    elif rnd < 12: amount = 250
    elif rnd < 32: amount = 100
    elif rnd < 62: amount = 50
    elif rnd < 87: amount = 20
    else: amount = 0
    set_user(uid, balance=d["balance"] + amount, wheel_time=now + 3600, wheel_daily=d["wheel_daily"] + 1)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.post("/ad")
def ad(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if now - d["last_ad"] < 60: raise HTTPException(400, "Подожди минуту")
    if d["balance"] >= 5000: raise HTTPException(400, "реклама доступна только при балансе < 5000")
    amount = random.choice([100, 200, 300, 500])
    set_user(uid, balance=d["balance"] + amount, last_ad=now)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.get("/")
def index():
    return FileResponse("index.html")
