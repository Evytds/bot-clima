import requests
import json
import os
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================
# CONFIGURACIÓN GENERAL - ADAPTADA A $40 Y METEO BOT
# ==========================
VERSION = "9.2-METEO-BOT-SIM"

CAPITAL_INICIAL = 40.00

EDGE_MIN = 0.0005          # Más sensible para capturar oportunidades
MAX_POSITION_PCT = 0.05    # 5% por trade (~$2 inicial)
MAX_OPEN_TRADES = 15
COMISION = 0.0             # Realista para Polymarket
MIN_LIQUIDITY = 20         # Acepta mercados más pequeños

GAMMA_API = "https://gamma-api.polymarket.com/markets"

CITIES = [
    "New York", "Toronto", "London", "Seattle",
    "Dallas", "Atlanta", "Chicago", "Los Angeles",
    "Buenos Aires", "Seoul", "Tokyo", "Sydney",
    "Boston", "Miami", "San Francisco"  # Ampliadas con comunes en weather
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
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
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
            "temperature", "temp", "degree", "degrees",
            "°", "c", "f", "above", "below", "reach",
            "exceed", "highest", "max", "between"
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
                        win_amount = t["stake"] / t["price"]
                        self.state["balance"] += win_amount
                        print(f"💰 GANADO | {t['city']} | +${win_amount - t['stake']:.2f}")
                    else:
                        print(f"❌ PERDIDO | {t['city']} | -${t['stake']:.2f}")
                else:
                    activos[market_id] = t
            except Exception:
                activos[market_id] = t

        self.state["open_trades"] = activos

    # ---------- ESCANEO ----------
    def scan_markets(self):
        print("🌦️ Escaneando Weather Markets (inspirado en Meteorological Bot)...")

        for city in CITIES:
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                print("⚠️ Límite de trades abiertos alcanzado")
                break

            try:
                markets = self.session.get(
                    GAMMA_API,
                    params={"active": "true", "query": city, "limit": 30},
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
                        print(f"⏩ Skip {city}: baja liquidez (${liquidity})")
                        continue

                    prices = json.loads(m.get("outcomePrices", "[]"))
                    if len(prices) != 2:
                        print(f"⏩ Skip {city}: no binario")
                        continue

                    p_yes, p_no = float(prices[0]), float(prices[1])

                    if not (0.01 < p_yes < 0.99 and 0.01 < p_no < 0.99):
                        print(f"⏩ Skip {city}: precios extremos")
                        continue

                    edge = abs(1 - (p_yes + p_no))
                    if edge < EDGE_MIN:
                        print(f"⏩ Skip {city}: edge bajo ({edge*100:.3f}%)")
                        continue

                    # Preferencia por "NO" si está barato (inspirado en el bot)
                    if p_no < 0.60 and p_no < p_yes:
                        side = "NO"
                        price = p_no
                    elif p_yes < 0.60:  # Fallback a YES barato
                        side = "YES"
                        price = p_yes
                    else:
                        continue  # Solo trades donde hay un lado claramente barato

                    stake = round(self.state["balance"] * MAX_POSITION_PCT, 2)
                    if stake < 0.5:  # Mínimo práctico
                        print("⚠️ Balance muy bajo para nuevos trades")
                        break

                    self.state["balance"] -= stake

                    net_win = round((stake / price - stake) * (1 - COMISION), 2)

                    self.state["open_trades"][mid] = {
                        "city": city,
                        "question": question,
                        "side": side,
                        "price": price,
                        "stake": stake,
                        "net_win": net_win,
                        "date": datetime.utcnow().isoformat()
                    }

                    print(
                        f"🎯 METEO TRADE | {city:<12} | {side} | "
                        f"Price {price:.2f} | Edge {edge*100:.2f}% | Stake ${stake}"
                    )
                    # Solo un trade por ciudad por ciclo (como original)
                    break

            except Exception as e:
                print(f"⚠️ Error en {city}: {e}")

    # ---------- RUN ----------
    def run(self):
        self.resolve_trades()
        self.scan_markets()
        self.state["history"].append(round(self.state["balance"], 2))
        self._save_state()
        print(f"✅ Ciclo terminado | Balance: ${self.state['balance']:.2f} | Trades abiertos: {len(self.state['open_trades'])}")


# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    PolyWeatherBot().run()
