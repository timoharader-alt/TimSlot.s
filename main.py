import hmac, hashlib, json, random, time, sqlite3, os
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН")
app = FastAPI()

def db():
    c = sqlite3.connect("slot.db")
    c.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, balance INTEGER DEFAULT 5000, wheel_time INTEGER DEFAULT 0, wheel_daily INTEGER DEFAULT 0, wheel_day INTEGER DEFAULT 0)")
    return c

def get_user(uid):
    c = db()
    row = c.execute("SELECT balance, wheel_time, wheel_daily, wheel_day FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        c.execute("INSERT INTO users(uid) VALUES(?)", (uid,))
        c.commit()
        row = (5000, 0, 0, 0)
    c.close()
    return {"balance": row[0], "wheel_time": row[1], "wheel_daily": row[2], "wheel_day": row[3]}

def set_user(uid, **kw):
    c = db()
    for k, v in kw.items(): c.execute(f"UPDATE users SET {k}=? WHERE uid=?", (v, uid))
    c.commit(); c.close()

def verify(init_data: str) -> dict:
    p = dict(parse_qsl(init_data, strict_parsing=True))
    h = p.pop("hash", None)
    if not h: raise HTTPException(400, "no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), h):
        raise HTTPException(401, "bad signature")
    return json.loads(p["user"])

GAMES = {
    "fruits": {
        "cols": 5, "rows": 3, "min_bet": 10,
        "symbols": [
            {"id":0, "pay":[10, 20, 100]}, {"id":1, "pay":[10, 20, 100]}, 
            {"id":2, "pay":[10, 30, 150]}, {"id":3, "pay":[10, 30, 150]}, 
            {"id":4, "pay":[20, 50, 200]}, {"id":5, "pay":[20, 50, 200]}, 
            {"id":6, "pay":[50, 200, 500]}, {"id":7, "pay":[100, 500, 1000]}
        ],
        "scatter": None
    },
    "space": {
        "cols": 7, "rows": 3, "min_bet": 50,
        "symbols": [
            {"id":0, "pay":[1.2, 2, 5]}, {"id":1, "pay":[1.5, 3, 6]}, 
            {"id":2, "pay":[2, 4, 8]}, {"id":3, "pay":[3, 6, 12]}, 
            {"id":4, "pay":[5, 10, 20]}, {"id":5, "pay":[10, 20, 50]}
        ],
        "scatter": 99
    },
    "egypt": {
        "cols": 5, "rows": 3, "min_bet": 50,
        "symbols": [
            {"id":0, "pay":[1.5, 3, 6]}, {"id":1, "pay":[2, 4, 8]}, 
            {"id":2, "pay":[3, 6, 12]}, {"id":3, "pay":[5, 10, 20]}, 
            {"id":4, "pay":[8, 16, 30]}, {"id":5, "pay":[15, 30, 60]}
        ],
        "scatter": 99
    }
}

LINES = {
    "fruits": [
        [1,1,1,1,1], [0,0,0,0,0], [2,2,2,2,2], [0,1,2,1,0], [2,1,0,1,2],
        [0,0,1,2,2], [2,2,1,0,0], [0,1,0,1,0], [2,1,2,1,2]
    ],
    "space": [
        [1,1,1,1,1,1,1], [0,0,0,0,0,0,0], [2,2,2,2,2,2,2],
        [0,1,2,1,0,1,0], [2,1,0,1,2,1,2], [0,0,1,2,2,1,0]
    ],
    "egypt": [
        [1,1,1,1,1], [0,0,0,0,0], [2,2,2,2,2], [0,1,2,1,0], [2,1,0,1,2]
    ]
}

def generate_grid(game_key):
    g = GAMES[game_key]
    cols, rows = g["cols"], g["rows"]
    weights = [40, 35, 30, 25, 15, 10, 5, 2]
    pool = [s["id"] for s in g["symbols"] for _ in range(weights[s["id"]])]
    
    grid = []
    for _ in range(cols):
        col = []
        for _ in range(rows):
            if g["scatter"] is not None and random.random() < 0.005:
                col.append(g["scatter"])
            else:
                col.append(random.choice(pool))
        grid.append(col)
    return grid

def check_win(grid, game_key, bet):
    g = GAMES[game_key]
    lines = LINES[game_key]
    total_win = 0
    win_lines = []
    scatters = 0

    if g["scatter"] is not None:
        for col in grid:
            for sym in col:
                if sym == g["scatter"]: scatters += 1

    for line_idx, line in enumerate(lines):
        first_sym = grid[0][line[0]]
        if first_sym == g["scatter"]: continue
        
        count = 1
        for col in range(1, len(grid)):
            if grid[col][line[col]] == first_sym: count += 1
            else: break
        
        if count >= 3:
            sym_data = next(s for s in g["symbols"] if s["id"] == first_sym)
            if count == 3: mult = sym_data["pay"][0]
            elif count == 4: mult = sym_data["pay"][1]
            else: mult = sym_data["pay"][2]
            
            payout = bet * mult
            total_win += payout
            win_lines.append({"line": line_idx, "count": count, "win": payout})
            
    return total_win, win_lines, scatters

class Req(BaseModel):
    init_data: str

@app.post("/state")
def state(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    today = int(time.strftime("%j"))
    
    if d["wheel_day"] != today:
        set_user(uid, wheel_daily=0, wheel_day=today)
        d["wheel_daily"] = 0

    can_wheel = (d["wheel_daily"] < 5) and (now >= d["wheel_time"])
    time_left = max(0, d["wheel_time"] - now)

    return {
        "balance": d["balance"], 
        "wheel_ready": can_wheel,
        "wheel_time_left": time_left,
        "wheel_daily": d["wheel_daily"],
        "ad_ready": now - d["wheel_time"] > 60,
        "ad_allowed": d["balance"] < 5000
    }

class SpinReq(BaseModel):
    init_data: str
    bet: int
    game: str
    bonus_buy: bool = False

@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    
    game_conf = GAMES[r.game]
    cost = r.bet * 100 if r.bonus_buy else r.bet
    
    if r.bet < game_conf["min_bet"]:
        raise HTTPException(400, f"Минимальная ставка {game_conf['min_bet']} фишек")
    if d["balance"] < cost:
        raise HTTPException(400, "Недостаточно фишек")

    bal = d["balance"] - cost
    grid = generate_grid(r.game)
    scatters = 0
    
    if r.bonus_buy:
        grid[1][0] = 99
        grid[3][1] = 99
        grid[2][2] = 99
        scatters = 3

    win_amount, win_lines, scatters_nat = check_win(grid, r.game, r.bet)
    if not r.bonus_buy: scatters = scatters_nat
    
    bal += win_amount
    set_user(uid, balance=bal)
    
    bonus_mult = 1
    if scatters >= 3:
        bonus_mult = random.choice([2, 3, 5, 10])

    return {
        "grid": grid, "win": win_amount, "balance": bal, "lines": win_lines, 
        "scatters": scatters, "bonus_mult": bonus_mult
    }

@app.post("/bonus")
def bonus(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    
    if d["wheel_daily"] >= 5: raise HTTPException(400, "Лимит 5 круток в день")
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
    return {"amount": amount, "balance": d["balance"] + amount, "next_wheel": now + 3600}

@app.post("/ad")
def ad(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if d["balance"] >= 5000: raise HTTPException(400, "реклама доступна только при балансе < 5000")
    amount = random.choice([100, 200, 300, 500])
    set_user(uid, balance=d["balance"] + amount)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.get("/")
def index():
    return FileResponse("index.html")
