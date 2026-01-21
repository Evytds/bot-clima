import requests
import json
import os
import time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================
# CONFIGURACIÓN GENERAL - ADAPTADA A $40 Y METEO BOT
# ==========================
VERSION = "9.3-IMPROVED-METEO-BOT"

CAPITAL_INICIAL = 40.00

EDGE_MIN = 0.0005  # Más sensible para capturar oportunidades
MAX_POSITION_PCT_BASE = 0.05  # 5% base por trade (~$2 inicial)
MAX_POSITION_PCT_MAX = 0.10   # Hasta 10% para high-edge trades
MAX_OPEN_TRADES = 15
COMISION = 0.001  # 0.1% realista para Polymarket (ajustable a 0 para sim pura)
MIN_LIQUIDITY = 50  # Aumentado para mercados más seguros

GAMMA_API = "https://gamma-api.polymarket.com/markets"

CITIES = [
    "New York", "New York City", "Toronto", "London", "Seattle",
    "Dallas", "Atlanta", "Chicago", "Los Angeles",
    "Buenos Aires", "Seoul", "Tokyo", "Sydney",
    "Boston", "Miami", "San Francisco"
    # Ampliadas con ciudades del perfil bot (e.g., New York City, Seoul, Atlanta, etc.)
]

# ==========================
# BOT
# ==========================
class PolyWeatherBot:
    def __init__(self):
        self.session = self._session()
        self.state = self._load_state()
        self.initial_balance = self.state.get('initial_balance', CAPITAL_INICIAL)  # Track initial for ROI
        print(f"🚀 {VERSION} | Balance simulado: ${self.state['balance']:.2f} | Inicial: ${self.initial_balance:.2f}")

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
            "initial_balance": CAPITAL_INICIAL,
            "open_trades": {},
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "history": []
        }

    def _save_state(self):
        with open("state.json", "w") as f:
            json.dump(self.state, f, indent=2)

    # ---------- FILTRO CLIMA (Mejorado para rangos estrechos como en el perfil) ----------
    def is_weather_market(self, question):
        q = question.lower()
        keywords = [
            "temperature", "temp", "degree", "degrees",
            "°", "c", "f", "above", "below", "reach",
            "exceed", "highest", "max", "between", "exact", "range"  # Añadido para detectar rangos como "42–43°F"
        ]
        return any(k in q for k in keywords)

    # ---------- RESOLVER TRADES (Mejorado con contadores) ----------
    def resolve_trades(self):
        if not self.state["open_trades"]:
            return

        active = {}
        resolved_count = 0
        for market_id, t in self.state["open_trades"].items():
            try:
                r = self.session.get(f"{GAMMA_API}/{market_id}", timeout=10).json()
                if r.get("closed") is True:
                    winner = r.get("winnerOutcomeIndex")
                    winner_side = "YES" if str(winner) == "0" else "NO"  # 0=YES, 1=NO en binarios
                    self.state["total_trades"] += 1
                    resolved_count += 1
                    if t["side"] == winner_side:
                        win_amount = t["stake"] / t["price"]
                        profit = win_amount - t["stake"]
                        self.state["balance"] += profit
                        self.state["wins"] += 1
                        print(f"💰 GANADO | {t['city']} | +${profit:.2f} (Net: ${t['net_win']:.2f})")
                    else:
                        self.state["losses"] += 1
                        print(f"❌ PERDIDO | {t['city']} | -${t['stake']:.2f}")
                else:
                    active[market_id] = t
            except Exception as e:
                print(f"⚠️ Error resolviendo trade {market_id}: {e}")
                active[market_id] = t

        self.state["open_trades"] = active
        if resolved_count > 0:
            win_rate = (self.state["wins"] / self.state["total_trades"] * 100) if self.state["total_trades"] > 0 else 0
            roi = ((self.state["balance"] - self.initial_balance) / self.initial_balance * 100) if self.initial_balance > 0 else 0
            print(f"📊 Resueltos: {resolved_count} | Win Rate: {win_rate:.1f}% | ROI: {roi:.2f}%")

    # ---------- ESCANEO (Mejorado con stake dinámico y bias NO fuerte) ----------
    def scan_markets(self):
        print("🌦️ Escaneando Weather Markets (inspirado en Meteo Bot del perfil)...")

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
                        print(f"⏩ Skip {city}: baja liquidez (${liquidity:.2f})")
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

                    # Fuerte bias a "NO" si barato, como en el perfil (prioridad a rangos estrechos)
                    is_narrow_range = any(k in question.lower() for k in ["exact", "range", "–", "between"])  # Detecta rangos como "42–43°F"
                    if p_no < 0.60 and (p_no < p_yes or is_narrow_range):  # Prefer NO, especialmente en rangos
                        side = "NO"
                        price = p_no
                    elif p_yes < 0.60:
                        side = "YES"
                        price = p_yes
                    else:
                        continue

                    # Stake dinámico: base 5%, escalado por edge (max 10%)
                    position_pct = MAX_POSITION_PCT_BASE + (edge * 100) * 0.01  # Ej: edge 0.01 -> +1% pct
                    position_pct = min(position_pct, MAX_POSITION_PCT_MAX)
                    stake = round(self.state["balance"] * position_pct, 2)
                    if stake < 1.0:  # Mínimo práctico
                        print("⚠️ Balance muy bajo para nuevos trades")
                        break

                    self.state["balance"] -= stake

                    # Net win ajustado por comisión
                    gross_win = stake / price - stake
                    net_win = round(gross_win * (1 - COMISION), 2)

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
                        f"Price {price:.2f} | Edge {edge*100:.2f}% | Stake ${stake:.2f} | Narrow? {is_narrow_range}"
                    )
                    # Solo un trade por ciudad por ciclo
                    break

            except Exception as e:
                print(f"⚠️ Error en {city}: {e}")

    # ---------- RUN ----------
    def run(self):
        self.resolve_trades()
        self.scan_markets()
        win_rate = (self.state["wins"] / self.state["total_trades"] * 100) if self.state["total_trades"] > 0 else 0
        roi = ((self.state["balance"] - self.initial_balance) / self.initial_balance * 100) if self.initial_balance > 0 else 0
        self.state["history"].append({
            "balance": round(self.state["balance"], 2),
            "win_rate": round(win_rate, 2),
            "roi": round(roi, 2),
            "open_trades": len(self.state["open_trades"]),
            "timestamp": datetime.utcnow().isoformat()
        })
        self._save_state()
        print(f"✅ Ciclo terminado | Balance: ${self.state['balance']:.2f} | Win Rate: {win_rate:.1f}% | ROI: {roi:.2f}% | Trades abiertos: {len(self.state['open_trades'])}")

# ==========================
# MAIN (Mejorado con múltiples ciclos para simulación)
# ==========================
if __name__ == "__main__":
    bot = PolyWeatherBot()
    num_cycles = 5  # Número de ciclos de simulación (ajusta o comenta para uno solo)
    for i in range(num_cycles):
        print(f"\n--- Ciclo {i+1}/{num_cycles} ---")
        bot.run()
        if i < num_cycles - 1:
            time.sleep(5)  # Pausa simulada entre ciclos (5s)
