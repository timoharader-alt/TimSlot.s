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
        referrer_id INTEGER DEFAULT 0, ref_count INTEGER DEFAULT 0
    )""")
    return c

def get_user(uid):
    c = db()
    row = c.execute("SELECT balance, wheel_time, wheel_daily, wheel_day, free_spins, xp, level, referrer_id, ref_count FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        c.execute("INSERT INTO users(uid, balance) VALUES(?, 5000)", (uid,))
        c.commit()
        row = (5000, 0, 0, 0, 0, 0, 1, 0, 0)
    c.close()
    return {"balance": row[0], "wheel_time": row[1], "wheel_daily": row[2], "wheel_day": row[3], "free_spins": row[4], "xp": row[5], "level": row[6], "referrer_id": row[7], "ref_count": row[8]}

def set_user(uid, **kw):
    c = db()
    for k, v in kw.items(): c.execute(f"UPDATE users SET {k}=? WHERE uid=?", (v, uid))
    c.commit(); c.close()

def verify(init_data: str) -> dict:
    if not BOT_TOKEN: raise HTTPException(500, "BOT_TOKEN не задан")
    p = dict(parse_qsl(init_data, strict_parsing=True))
    h = p.pop("hash", None)
    if not h: raise HTTPException(400, "no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), h):
        raise HTTPException(401, "bad signature")
    return json.loads(p["user"])

GAMES = {
    "fruits": {"cols": 3, "rows": 1, "min_bet": 10, "symbols": [{"id":0, "pay":[0, 10, 30]}, {"id":1, "pay":[0, 15, 50]}, {"id":2, "pay":[0, 20, 100]}, {"id":3, "pay":[0, 50, 200]}, {"id":4, "pay":[0, 100, 500]}, {"id":5, "pay":[0, 200, 1000]}], "scatter": None},
    "space": {"cols": 7, "rows": 3, "min_bet": 10, "symbols": [{"id":0, "pay":[1.2, 2, 5]}, {"id":1, "pay":[1.5, 3, 6]}, {"id":2, "pay":[2, 4, 8]}, {"id":3, "pay":[3, 6, 12]}, {"id":4, "pay":[5, 10, 20]}, {"id":5, "pay":[10, 20, 50]}], "scatter": 99},
    "egypt": {"cols": 5, "rows": 3, "min_bet": 10, "symbols": [{"id":0, "pay":[1.5, 3, 6]}, {"id":1, "pay":[2, 4, 8]}, {"id":2, "pay":[3, 6, 12]}, {"id":3, "pay":[5, 10, 20]}, {"id":4, "pay":[8, 16, 30]}, {"id":5, "pay":[15, 30, 60]}], "scatter": 99},
    "fishing": {"cols": 5, "rows": 3, "min_bet": 10, "symbols": [{"id":0, "pay":[5, 25, 100]}, {"id":1, "pay":[5, 25, 100]}, {"id":2, "pay":[5, 25, 100]}, {"id":3, "pay":[5, 25, 100]}, {"id":4, "pay":[5, 25, 100]}, {"id":5, "pay":[10, 50, 200]}, {"id":6, "pay":[20, 100, 500]}, {"id":7, "pay":[20, 100, 500]}, {"id":8, "pay":[30, 150, 1000]}, {"id":9, "pay":[50, 200, 2000]}], "scatter": 10, "wild": 11, "fish_cash": [12, 13, 14, 15]}
}

LINES = {
    "fruits": [[0,0,0]],
    "space": [[1,1,1,1,1,1,1], [0,0,0,0,0,0,0], [2,2,2,2,2,2,2], [0,1,2,1,0,1,0], [2,1,0,1,2,1,2], [0,0,1,2,2,1,0]],
    "egypt": [[1,1,1,1,1], [0,0,0,0,0], [2,2,2,2,2], [0,1,2,1,0], [2,1,0,1,2]],
    "fishing": [[1,1,1,1,1], [0,0,0,0,0], [2,2,2,2,2], [0,1,2,1,0], [2,1,0,1,2], [0,0,1,2,2], [2,2,1,0,0], [0,1,2,2,2], [2,1,0,0,0], [0,0,1,0,0]]
}

FISH_CASH_VALUES = [2, 5, 10, 15, 20, 25, 50, 200]

def generate_grid(game_key):
    g = GAMES[game_key]
    cols, rows = g["cols"], g["rows"]
    grid = [[None]*rows for _ in range(cols)]
    
    if game_key == "fishing":
        for c in range(cols):
            for r in range(rows):
                rand = random.random()
                if rand < 0.01: grid[c][r] = g["scatter"]
                elif rand < 0.06: grid[c][r] = random.choice(g["fish_cash"])
                else: grid[c][r] = random.choice(range(10))
        return grid

    weights = [60, 50, 40, 30, 15, 5]
    pool = [s["id"] for s in g["symbols"] for _ in range(weights[s["id"]] if s["id"] < len(weights) else 1)]
    for _ in range(cols):
        col = []
        for _ in range(rows):
            if g["scatter"] is not None and random.random() < 0.015: col.append(g["scatter"])
            else: col.append(random.choice(pool))
        grid[_] = col
    return grid

def check_win(grid, game_key, bet, free_spins=0, fish_caught=0):
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
                if sym == g["scatter"]: scatters += 1

    if game_key == "fishing":
        wild_coords = [(c, r) for c in range(len(grid)) for r in range(len(grid[c])) if grid[c][r] == g["wild"]]
        wilds_count = len(wild_coords)
        
        if wilds_count >= 1 and free_spins > 0:
            mult = 1
            if fish_caught >= 9: mult = 10
            elif fish_caught >= 6: mult = 5
            elif fish_caught >= 3: mult = 3
            elif fish_caught >= 1: mult = 2
            
            for c in range(len(grid)):
                for r in range(len(grid[c])):
                    if grid[c][r] in g["fish_cash"]:
                        val = random.choice([2, 5, 10, 20, 50, 100]) * bet
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
                first_sym = sym
                count += 1
            else: break
        
        min_match = 2 if game_key == "fruits" else 3
        
        if count >= min_match:
            if game_key == "fishing":
                sym_data = g["symbols"][first_sym] if first_sym < 10 else g["symbols"][0]
                mult = sym_data["pay"][count-3] if count >= 3 else 0
            else:
                sym_data = next(s for s in g["symbols"] if s["id"] == first_sym)
                idx = count - min_match
                if idx < len(sym_data["pay"]):
                    mult = sym_data["pay"][idx]
                else:
                    mult = sym_data["pay"][-1]
            
            payout = bet * mult
            total_win += payout
            win_lines.append({"line": line_idx, "count": count, "win": payout})
            
    return total_win, win_lines, scatters, fish_data, wilds_count

class Req(BaseModel): init_data: str
class RefReq(BaseModel): init_data: str; referrer_id: int
class SpinReq(BaseModel): init_data: str; bet: int; game: str; bonus_buy: bool = False; free_spins: int = 0; fish_caught: int = 0

@app.post("/state")
def state(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    today = int(time.strftime("%j"))
    if d["wheel_day"] != today:
        set_user(uid, wheel_daily=0, wheel_day=today)
        d["wheel_daily"] = 0
    can_wheel = (d["wheel_daily"] < 5) and (now >= d["wheel_time"])
    time_left = max(0, d["wheel_time"] - now)
    return {"balance": d["balance"], "wheel_ready": can_wheel, "wheel_time_left": time_left, "wheel_daily": d["wheel_daily"], "ad_ready": now - d["wheel_time"] > 60, "ad_allowed": d["balance"] < 5000, "free_spins": d["free_spins"], "level": d["level"], "xp": d["xp"], "next_level_xp": d["level"] * 15000, "ref_count": d["ref_count"]}

@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    game_conf = GAMES[r.game]
    is_fs = d["free_spins"] > 0
    cost = 0 if is_fs else (r.bet * 15 if r.bonus_buy else r.bet)
    
    if not is_fs and r.bet < game_conf["min_bet"]: raise HTTPException(400, f"Мин. ставка {game_conf['min_bet']}")
    if d["balance"] < cost: raise HTTPException(400, "Недостаточно фишек")

    bal = d["balance"] - cost
    grid = generate_grid(r.game)
    scatters = 0
    
    if r.bonus_buy:
        for c in range(len(grid)):
            for row in range(len(grid[c])):
                if grid[c][row] == game_conf.get("scatter"): grid[c][row] = 0
        grid[1][0] = game_conf["scatter"]; grid[3][1] = game_conf["scatter"]; grid[2][2] = game_conf["scatter"]
        scatters = 3
    else:
        if not is_fs and game_conf.get("scatter") is not None:
            for c in grid:
                for sym in c:
                    if sym == game_conf["scatter"]: scatters += 1
        elif is_fs:
             for c in range(len(grid)):
                for row in range(len(grid[c])):
                    if grid[c][row] == game_conf.get("scatter"): grid[c][row] = 0

    win_amount, win_lines, scatters_nat, fish_data, wilds_count = check_win(grid, r.game, r.bet, d["free_spins"], r.fish_caught)
    if not r.bonus_buy and not is_fs: scatters = scatters_nat
    
    new_free_spins = d["free_spins"]
    new_fish_caught = r.fish_caught
    
    if is_fs:
        new_free_spins -= 1
        if wilds_count > 0:
            new_fish_caught += wilds_count
            if new_fish_caught % 3 == 0 and new_fish_caught <= 12:
                new_free_spins += 10
    elif scatters >= 3:
        new_free_spins = 10
        new_fish_caught = 0
        # ГАРАНТИЯ 30% ДЛЯ КУПЛЕННОГО БОНУСА
        if r.bonus_buy:
            min_guaranteed = cost * 0.3
            if win_amount < min_guaranteed:
                win_amount = int(min_guaranteed)
    
    bal += win_amount
    new_xp = d["xp"] + win_amount 
    new_level = d["level"]
    next_level_xp = new_level * 15000
    if new_xp >= next_level_xp:
        new_level += 1
        bal += 5000
        new_xp = new_xp - next_level_xp
        
    set_user(uid, balance=bal, free_spins=new_free_spins, xp=new_xp, level=new_level)
    
    ui_mult = 1
    if new_fish_caught >= 9: ui_mult = 10
    elif new_fish_caught >= 6: ui_mult = 5
    elif new_fish_caught >= 3: ui_mult = 3
    elif new_fish_caught >= 1: ui_mult = 2

    return {"grid": grid, "win": win_amount, "balance": bal, "lines": win_lines, "scatters": scatters, "bonus_mult": ui_mult, "fish_data": fish_data, "is_free_spin": is_fs, "free_spins_left": new_free_spins, "fish_caught": new_fish_caught, "level": new_level, "xp": new_xp}

# ... ОСТАЛЬНЫЕ ЭНДПОИНТЫ (referral, bonus, ad, index) ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ, КАК В ПРОШЛОМ СООБЩЕНИИ ...
