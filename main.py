import hmac, hashlib, json, random, time, sqlite3, os
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Вставь сюда свой токен от BotFather (внутри кавычек)
BOT_TOKEN = os.getenv("BOT_TOKEN", "9110201643:AAG67oiLoDzt2pVrQggRB6OZHafInMypKLA")
app = FastAPI()

def db():
    c = sqlite3.connect("slot.db")
    c.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, balance INTEGER DEFAULT 500, last_bonus INTEGER DEFAULT 0, last_ad INTEGER DEFAULT 0)")
    return c

def get_user(uid):
    c = db()
    row = c.execute("SELECT balance,last_bonus,last_ad FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        c.execute("INSERT INTO users(uid) VALUES(?)", (uid,))
        c.commit()
        row = (500, 0, 0)
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

SYMBOLS = [{"s": "🍒", "w": 40, "pay": 2}, {"s": "🍋", "w": 30, "pay": 3}, {"s": "🔔", "w": 20, "pay": 5}, {"s": "💎", "w": 10, "pay": 15}]
POOL = [o for o in SYMBOLS for _ in range(o["w"])]

def payout(reels):
    if reels[0]["s"] == reels[1]["s"] == reels[2]["s"]: return reels[0]["pay"] * 10
    if reels[0]["s"] == reels[1]["s"] or reels[1]["s"] == reels[2]["s"] or reels[0]["s"] == reels[2]["s"]: return 2
    return 0

class Req(BaseModel):
    init_data: str

@app.post("/state")
def state(r: Req):
    u = verify(r.init_data); d = get_user(u["id"]); now = int(time.time())
    return {"balance": d["balance"], "bonus_ready": now - d["last_bonus"] > 86400, "ad_ready": now - d["last_ad"] > 60, "ad_allowed": d["balance"] < 2500}

class SpinReq(BaseModel):
    init_data: str
    bet: int = 10

@app.post("/spin")
def spin(r: SpinReq):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid)
    if r.bet <= 0 or d["balance"] < r.bet: raise HTTPException(400, "мало фишек")
    bal = d["balance"] - r.bet
    reels = [random.choice(POOL) for _ in range(3)]
    win = payout(reels) * r.bet // 10
    bal += win; set_user(uid, balance=bal)
    return {"reels": [x["s"] for x in reels], "win": win, "balance": bal}

@app.post("/bonus")
def bonus(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if now - d["last_bonus"] < 86400: raise HTTPException(400, "бонус уже получен")
    amount = random.choice([100, 200, 300, 500, 700, 1000])
    set_user(uid, balance=d["balance"] + amount, last_bonus=now)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.post("/ad")
def ad(r: Req):
    u = verify(r.init_data); uid = u["id"]; d = get_user(uid); now = int(time.time())
    if d["balance"] >= 2500: raise HTTPException(400, "реклама недоступна")
    if now - d["last_ad"] < 60: raise HTTPException(400, "подожди минуту")
    amount = random.choice([100, 200, 300, 500])
    set_user(uid, balance=d["balance"] + amount, last_ad=now)
    return {"amount": amount, "balance": d["balance"] + amount}

@app.get("/")
def index():
    return FileResponse("index.html")
