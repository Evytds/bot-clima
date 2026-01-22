import requests
import json
import os
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================
# CONFIGURACIÓN GENERAL (usa environment variables para secrets)
# ==========================
VERSION = "9.1-POLY-WEATHER-LIVE-SCAN"
CAPITAL_INICIAL = float(os.getenv('CAPITAL_INICIAL', 196.70))
EDGE_MIN = float(os.getenv('EDGE_MIN', 0.0015)) # 0.15% → permite operar sin forzar
MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_PCT', 0.02)) # 2% por trade
MAX_OPEN_TRADES = int(os.getenv('MAX_OPEN_TRADES', 10))
COMISION = float(os.getenv('COMISION', 0.02))
MIN_LIQUIDITY = float(os.getenv('MIN_LIQUIDITY', 50)) # Clima suele tener liquidez baja
GAMMA_API = "https://gamma-api.polymarket.com/markets"
CLOB_API = "https://clob.polymarket.com"
CITIES = [
    "New York", "Toronto", "London", "Seattle",
    "Dallas", "Atlanta", "Chicago",
    "Los Angeles", "Buenos Aires",
    "Seoul", "Tokyo", "Sydney"
]

# ==========================
# BOT
# ==========================
class PolyWeatherBot:
    def __init__(self):
        self.session = self._session()
        self.state = self._load_state()
        print(f"🚀 {VERSION} | Balance simulado: ${self.state['balance']:.2f}")

    # ---------- SESSION ----------
    def _session(self):
        s = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    # ---------- STATE ----------
    def _load_state(self):
        if os.path.exists("state.json"):
            try:
                with open("state.json", "r") as f:
                    return json.load(f)
            except Exception:
                print("⚠️ state.json corrupto — reiniciando")
        return {
            "balance": CAPITAL_INICIAL,
            "open_trades": {},
            "history": []
        }

    def _save_state(self):
        with open("state.json", "w") as f:
            json.dump(self.state, f, indent=2)

    # ---------- FILTRO CLIMA ----------
    def is_weather_market(self, question):
        q = question.lower()
        keywords = [
            "temperature", "temp",
            "degree", "degrees",
            "°", "c", "f",
            "above", "below",
            "reach", "exceed",
            "highest", "max"
        ]
        return any(k in q for k in keywords)

    # ---------- RESOLVER TRADES ----------
    def resolve_trades(self):
        if not self.state["open_trades"]:
            return
        activos = {}
        for market_id, t in self.state["open_trades"].items():
            try:
                r = self.session.get(f"{GAMMA_API}/{market_id}", timeout=10).json()
                if r.get("closed") is True:
                    winner = r.get("winnerOutcomeIndex")
                    winner_side = "YES" if str(winner) == "0" else "NO"
                    if t["side"] == winner_side:
                        self.state["balance"] += t["stake"] + t["net_win"]
                        print(f"💰 GANADO | {t['city']} | +${t['net_win']:.2f}")
                    else:
                        print(f"❌ PERDIDO | {t['city']} | -${t['stake']:.2f}")
                else:
                    activos[market_id] = t
            except Exception:
                activos[market_id] = t
        self.state["open_trades"] = activos

    # ---------- GET YES NO MID PRICES (CLOB for real prices) ----------
    def get_yes_no_mid(self, market):
        clob_tokens = json.loads(market.get("clobTokenIds", "[]"))
        if not clob_tokens or len(clob_tokens) != 2:
            return None, None
        
        yes_token = clob_tokens[0]  # YES
        no_token = clob_tokens[1]  # NO
        
        def fetch_mid(token):
            try:
                r = self.session.get(f"{CLOB_API}/midpoint?token_id={token}", timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    mid_str = data.get("midpoint", None)
                    return float(mid_str) if mid_str else None
            except:
                return None
        
        p_yes = fetch_mid(yes_token)
        p_no = fetch_mid(no_token)
        
        return p_yes, p_no

    # ---------- ESCANEO ----------
    def scan_markets(self):
        print("🌦️ Escaneando Weather Session (Polymarket)...")
        for city in CITIES:
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                break
            try:
                markets = self.session.get(
                    GAMMA_API,
                    params={
                        "active": "true",
                        "search": city,
                        "limit": 25,
                        "closed": "false"
                    },
                    timeout=15
                ).json()
                for m in markets:
                    mid = m.get("id")
                    if not mid or mid in self.state["open_trades"]:
                        continue
                    question = m.get("question", "")
                    if not self.is_weather_market(question):
                        continue
                    liquidity = float(m.get("liquidity", 0))
                    if liquidity < MIN_LIQUIDITY:
                        continue
                    p_yes, p_no = self.get_yes_no_mid(m)
                    if p_yes is None or p_no is None or not (0.01 < p_yes < 0.99):
                        continue
                    edge = abs(1 - (p_yes + p_no))
                    if edge < EDGE_MIN:
                        continue
                    side = "YES" if p_yes < 0.5 else "NO"
                    price = p_yes if side == "YES" else p_no
                    stake = round(self.state["balance"] * MAX_POSITION_PCT, 2)
                    if stake < 0.5:
                        continue
                    self.state["balance"] -= stake
                    self.state["open_trades"][mid] = {
                        "city": city,
                        "question": question,
                        "side": side,
                        "price": price,
                        "stake": stake,
                        "net_win": round((stake / price - stake) * (1 - COMISION), 2),
                        "date": datetime.utcnow().isoformat()
                    }
                    print(
                        f"🎯 WEATHER TRADE | {city:<12} | {side} | "
                        f"Price {price:.2f} | Edge {edge*100:.2f}% | Stake ${stake}"
                    )
                    break
            except Exception as e:
                print(f"⚠️ Error en {city}: {e}")

    # ---------- RUN ----------
    def run(self):
        self.resolve_trades()
        self.scan_markets()
        self.state["history"].append(round(self.state["balance"], 2))
        self._save_state()
        print(f"✅ Ciclo terminado | Balance: ${self.state['balance']:.2f}")

# ==========================
# BACKTEST
# ==========================
    def backtest(self, start_date, end_date):
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        while current <= end:
            print(f"📅 Backtest para {current.strftime('%Y-%m-%d')}")
            self.scan_markets()  # Adaptar para historical si es posible
            self.resolve_trades()
            current += timedelta(days=1)
            time.sleep(1)  # Para no spamear

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    bot = PolyWeatherBot()
    bot.run()  # Para loop infinito: while True: bot.run(); time.sleep(600)
    # Para backtest: bot.backtest("2025-01-01", "2026-01-01")
