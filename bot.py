import requests
import json
import os
import re
import math
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================
# CONFIGURACIÓN MAESTRA
# ==========================
VERSION = "8.0-CLIMATE-OPTIMIZED"
CAPITAL_INICIAL = 196.70

EDGE_MIN = 0.015           # 1.5% edge realista
MAX_POSITION_PCT = 0.025   # 2.5% por trade
MAX_OPEN_TRADES = 10
COMISION = 0.02
MIN_LIQUIDITY = 500        # Permite más frecuencia sin basura

CITIES = [
    "New York", "Toronto", "London", "Seoul", "Atlanta", "Dallas",
    "Seattle", "Buenos Aires", "Chicago", "Los Angeles", "Tokyo", "Sydney"
]

GAMMA_API = "https://gamma-api.polymarket.com/markets"

# ==========================
# BOT
# ==========================
class ClimateTraderOptimized:

    def __init__(self):
        self.session = self._session()
        self.state = self._load_state()
        print(f"🚀 {VERSION} | Balance importing: ${self.state['balance']:.2f}")

    # ---------- SESSION ----------
    def _session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    # ---------- STATE ----------
    def _load_state(self):
        if os.path.exists("state.json"):
            try:
                with open("state.json", "r") as f:
                    return json.load(f)
            except Exception:
                print("⚠️ state.json corrupto — reiniciando estado")
        return {
            "balance": CAPITAL_INICIAL,
            "open_trades": {},
            "history": []
        }

    def _save_state(self):
        with open("state.json", "w") as f:
            json.dump(self.state, f, indent=2)

    # ---------- RESOLVER TRADES ----------
    def resolve_trades(self):
        if not self.state["open_trades"]:
            return

        print(f"🔄 Resolviendo {len(self.state['open_trades'])} trades abiertos...")
        activos = {}

        for market_id, t in self.state["open_trades"].items():
            try:
                r = self.session.get(f"{GAMMA_API}/{market_id}", timeout=10).json()

                if r.get("closed") is True:
                    winner = r.get("winnerOutcomeIndex")
                    winner_side = "YES" if str(winner) == "0" else "NO"

                    if t["side"] == winner_side:
                        payout = t["stake"] + t["net_win"]
                        self.state["balance"] += payout
                        print(f"💰 GANADO | {t['city']} | +${t['net_win']:.2f}")
                    else:
                        print(f"❌ PERDIDO | {t['city']} | -${t['stake']:.2f}")
                else:
                    activos[market_id] = t

            except Exception as e:
                print(f"⚠️ Error resolviendo {market_id}: {e}")
                activos[market_id] = t

        self.state["open_trades"] = activos

    # ---------- ESCANEO ----------
    def scan_markets(self):
        print(f"🔍 Escaneando {len(CITIES)} ciudades | Edge mínimo {EDGE_MIN*100:.1f}%")

        for city in CITIES:
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                break

            try:
                markets = self.session.get(
                    GAMMA_API,
                    params={"active": "true", "query": city, "limit": 25},
                    timeout=15
                ).json()

                for m in markets:
                    if m["id"] in self.state["open_trades"]:
                        continue

                    liquidity = float(m.get("liquidity", 0))
                    if liquidity < MIN_LIQUIDITY:
                        continue

                    prices = json.loads(m["outcomePrices"])
                    p_yes, p_no = float(prices[0]), float(prices[1])

                    if not (0.05 < p_yes < 0.95):
                        continue

                    # INEFICIENCIA SIMPLE (frecuencia)
                    edge = abs(1 - (p_yes + p_no))
                    if edge < EDGE_MIN:
                        continue

                    side = "YES" if p_yes < 0.5 else "NO"
                    price = p_yes if side == "YES" else p_no

                    stake = round(self.state["balance"] * MAX_POSITION_PCT, 2)
                    if stake < 0.5:
                        continue

                    self.state["balance"] -= stake
                    self.state["open_trades"][m["id"]] = {
                        "city": city,
                        "side": side,
                        "stake": stake,
                        "price": price,
                        "net_win": round((stake / price - stake) * (1 - COMISION), 2),
                        "expiry": m["endDate"].split("T")[0]
                    }

                    print(f"🎯 TRADE | {city:<12} | {side} | Edge {edge*100:.2f}% | Stake ${stake}")
                    break

            except Exception as e:
                print(f"⚠️ Error escaneando {city}: {e}")

    # ---------- RUN ----------
    def run(self):
        self.resolve_trades()
        self.scan_markets()
        self.state["history"].append(round(self.state["balance"], 2))
        self._save_state()
        print(f"✅ Ciclo finalizado | Balance: ${self.state['balance']:.2f}")


# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    ClimateTraderOptimized().run()
