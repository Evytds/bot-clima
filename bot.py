import requests
import json
import os
import re
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================
# CONFIGURACIÓN
# ==========================
VERSION = "9.0-POLY-WEATHER-SESSION"
CAPITAL_INICIAL = 196.70

EDGE_MIN = 0.003            # 0.3% edge (real en clima)
MAX_POSITION_PCT = 0.015    # 1.5% por trade
MAX_OPEN_TRADES = 15
COMISION = 0.02
MIN_LIQUIDITY = 50          # Clave: mercados pequeños

CITIES = [
    "New York", "Toronto", "London", "Seoul", "Atlanta", "Dallas",
    "Seattle", "Buenos Aires", "Chicago", "Los Angeles", "Tokyo", "Sydney"
]

GAMMA_API = "https://gamma-api.polymarket.com/markets"

# ==========================
# BOT
# ==========================
class PolyWeatherBot:

    def __init__(self):
        self.session = self._session()
        self.state = self._load_state()
        print(f"🚀 {VERSION} | Balance simulado: ${self.state['balance']:.2f}")

    def _session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429,500,502,503,504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _load_state(self):
        if os.path.exists("state.json"):
            try:
                with open("state.json","r") as f:
                    return json.load(f)
            except:
                print("⚠️ state.json corrupto — reiniciando")
        return {"balance": CAPITAL_INICIAL, "open_trades": {}, "history": []}

    def _save_state(self):
        with open("state.json","w") as f:
            json.dump(self.state, f, indent=2)

    # ==========================
    # FILTRO REAL DE CLIMA
    # ==========================
    def is_weather_market(self, question):
        q = question.lower()
        keywords = [
            "highest temperature", "temperature",
            "°c", "°f", "celsius", "fahrenheit"
        ]
        return any(k in q for k in keywords)

    # ==========================
    # RESOLVER
    # ==========================
    def resolve_trades(self):
        activos = {}
        for m_id, t in self.state["open_trades"].items():
            try:
                r = self.session.get(f"{GAMMA_API}/{m_id}", timeout=10).json()
                if r.get("closed") is True:
                    winner = "YES" if str(r.get("winnerOutcomeIndex")) == "0" else "NO"
                    if t["side"] == winner:
                        self.state["balance"] += t["stake"] + t["net_win"]
                        print(f"💰 GANADO | {t['city']} | +${t['net_win']:.2f}")
                    else:
                        print(f"❌ PERDIDO | {t['city']} | -${t['stake']:.2f}")
                else:
                    activos[m_id] = t
            except:
                activos[m_id] = t
        self.state["open_trades"] = activos

    # ==========================
    # ESCANEO WEATHER SESSION
    # ==========================
    def scan_weather(self):
        print("🌦️ Escaneando Weather Session (Polymarket)...")

        for city in CITIES:
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                break

            try:
                markets = self.session.get(
                    GAMMA_API,
                    params={"active":"true","query":city,"limit":40},
                    timeout=15
                ).json()

                for m in markets:
                    if m["id"] in self.state["open_trades"]:
                        continue

                    if not self.is_weather_market(m.get("question","")):
                        continue

                    liquidity = float(m.get("liquidity",0))
                    if liquidity < MIN_LIQUIDITY:
                        continue

                    prices = json.loads(m["outcomePrices"])
                    p_yes, p_no = float(prices[0]), float(prices[1])

                    # Permitimos micro-precios como el trader real
                    if not (0.01 <= p_yes <= 0.99):
                        continue

                    edge = abs(1 - (p_yes + p_no))
                    if edge < EDGE_MIN:
                        continue

                    side = "YES" if p_yes < 0.5 else "NO"
                    price = p_yes if side == "YES" else p_no

                    stake = round(self.state["balance"] * MAX_POSITION_PCT, 2)
                    if stake < 0.25:
                        continue

                    self.state["balance"] -= stake
                    self.state["open_trades"][m["id"]] = {
                        "city": city,
                        "side": side,
                        "stake": stake,
                        "net_win": round((stake / price - stake) * (1 - COMISION), 2),
                        "expiry": m["endDate"].split("T")[0]
                    }

                    print(
                        f"🎯 WEATHER TRADE | {city:<12} | {side:<3} "
                        f"| Price {price:.2f} | Edge {edge*100:.2f}% | Stake ${stake}"
                    )

                    if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                        break

            except Exception as e:
                print(f"⚠️ Error en {city}: {e}")

    # ==========================
    # RUN
    # ==========================
    def run(self):
        self.resolve_trades()
        self.scan_weather()
        self.state["history"].append(round(self.state["balance"],2))
        self._save_state()
        print(f"✅ Ciclo terminado | Balance: ${self.state['balance']:.2f}")

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    PolyWeatherBot().run()
