import hmac, hashlib, json, random, time, sqlite3, os
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН")
app = FastAPI()

def db():
    c = sqlite3.connect("slot.db")
    c.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, balance INTEGER DEFAULT 5000, last_bonus INTEGER DEFAULT 0, last_ad INTEGER DEFAULT 0)")
    return c

def get_user(uid):
    c = db()
    row = c.execute("SELECT balance,last_bonus,last_ad FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        c.execute("INSERT INTO users(uid) VALUES(?)", (uid,))
        c.commit()
        row = (5000, 0, 0)
    c.close()
    return {"balance": row[0], "last_bonus": row[1], "last_ad": row[2]}

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

# ИСПРАВЛЕНО: ID 99 для скаттера
GAMES = {
    "fruits": {
        "cols": 3, "rows": 1, 
        "symbols": [{"id":0,"pay":5}, {"id":1,"pay":10}, {"id":2,"pay":20}, {"id":3,"pay":50}, {"id":4,"pay":100}, {"id":5,"pay":200}],
        "scatter": None
    },
    "space": {
        "cols": 7, "rows": 3,
        "symbols": [{"id":0,"pay":2}, {"id":1,"pay":3}, {"id":2,"pay":4}, {"id":3,"pay":6}, {"id":4,"pay":10}, {"id":5,"pay":20}],
        "scatter": 99
    },
    "egypt": {
        "cols": 5, "rows": 3,
        "symbols": [{"id":0,"pay":5}, {"id":1,"pay":10}, {"id":2,"pay":15}, {"id":3,"pay":25}, {"id":4,"pay":50}, {"id":5,"pay":100}],
        "scatter": 99
    }
}

LINES = {
    "fruits": [[0,0,0]],
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
    weights = [50, 30, 20, 10, 5, 2]
    pool = [s["id"] for s in g["symbols"] for _ in range(weights[s["id"]])]
    
    grid = []
    for _ in range(cols):
        col = []
        for _ in range(rows):
            # ИСПРАВЛЕНО: Шанс 0.5% на ячейку. 
            # Для 7x3 это ~10% на то, что выпадет хотя бы 1 скаттер, 
            # и ~1% на то, что их выпадет 3 и больше (бонус).
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

    # Считаем скаттеры (проверяем именно ID 99)
    if g["scatter"] is not None:
        for col in grid:
            for sym in col:
                if sym == g["scatter"]: scatters += 1

    for line_idx, line in enumerate(lines):
        first_sym = grid[0][line[0]]
        if first_sym == g["scatter"]: continue # Скаттеры не участвуют в линиях
        count = 1
        for col in range(1, len(grid)):
            if grid[col][line[col]] == first_sym: count += 1
            else: break
        if count >= 3:
            sym_data = next(s for s in g["symbols"] if s["id"] == first_sym)
            payout = sym_data["pay"] * (bet // 10) * count
            total_win += payout
            win_lines.append({"line": line_idx, "count": count, "win": payout})
    return total_win, win_lines, scatters

class Req(BaseModel):
    init_data: str

@app.post("/state")
def state(r: Req):
    u = verify(r.init_data); d = get_user(u["id"]); now = int(time.time())
    return {"balance": d["balance"], "bonus_ready": now - d["last_bonus"] > 86400, "ad_ready": now - d["last_ad"] > 60, "ad_allowed": d["balance"] < 5000}

class SpinReq(BaseModel):
    init_data: str
    bet: int = 10
    game: str = "fruits"

@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if r.bet < 0 or d["balance"] < r.bet: raise HTTPException(400, "мало фишек")
    bal = d["balance"] - r.bet
    grid = generate_grid(r.game)
    calc_bet = r.bet if r.bet > 0 else 10
    win_amount, win_lines, scatters = check_win(grid, r.game, calc_bet)
    bal += win_amount
    set_user(uid, balance=bal)
    return {"grid": grid, "win": win_amount, "balance": bal, "lines": win_lines, "scatters": scatters}

@app.post("/bonus")
def bonus(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if now - d["last_bonus"] < 86400: raise HTTPException(400, "бонус уже получен")
    rnd = random.random() * 100
    if rnd < 2: amount = 1000
    elif rnd < 7: amount = 500
    elif rnd < 17: amount = 250
    elif rnd < 42: amount = 100
    elif rnd < 72: amount = 50
    elif rnd < 92: amount = 20
    else: amount = 0
    set_user(uid, balance=d["balance"] + amount, last_bonus=now)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.post("/ad")
def ad(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if d["balance"] >= 5000: raise HTTPException(400, "реклама недоступна")
    if now - d["last_ad"] < 60: raise HTTPException(400, "подожди минуту")
    amount = random.choice([100, 200, 300, 500])
    set_user(uid, balance=d["balance"] + amount, last_ad=now)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.get("/")
def index():
    return FileResponse("index.html")
