import requests
import json
import os
import re
import math
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ==========================
# CONFIGURACIÓN
# ==========================
VERSION = "7.1-PRO-HYBRID-EDGE"
CAPITAL_INICIAL = 196.70

EDGE_THRESHOLD = 0.04        # 4% edge mínimo
MAX_POSITION_PCT = 0.03     # 3% por trade
MAX_OPEN_TRADES = 6
COMISION = 0.02
EARLY_EXIT_EDGE = 0.04      # cerrar si el edge se reduce a +4%

GAMMA_API = "https://gamma-api.polymarket.com/markets"

CIUDADES = {
    "New York": {"lat": 40.71, "lon": -74.00},
    "Toronto": {"lat": 43.65, "lon": -79.38},
    "London": {"lat": 51.50, "lon": -0.12},
    "Seoul": {"lat": 37.56, "lon": 126.97},
    "Atlanta": {"lat": 33.74, "lon": -84.38},
    "Dallas": {"lat": 32.77, "lon": -96.79},
    "Seattle": {"lat": 47.60, "lon": -122.33},
    "Buenos Aires": {"lat": -34.60, "lon": -58.38},
    "Chicago": {"lat": 41.87, "lon": -87.62},
    "Los Angeles": {"lat": 34.05, "lon": -118.24},
    "Tokyo": {"lat": 35.68, "lon": 139.76},
    "Sydney": {"lat": -33.86, "lon": 151.20}
}

# ==========================
# BOT
# ==========================
class WeatherTraderPro:
    def __init__(self):
        self.session = self._config_session()
        self.state = self._load_state()
        os.makedirs("reports", exist_ok=True)
        print(f"🚀 {VERSION} | Balance: ${self.state['balance']:.2f}")

    def _config_session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _load_state(self):
        if os.path.exists("state.json"):
            with open("state.json", "r") as f:
                return json.load(f)
        return {"balance": CAPITAL_INICIAL, "open_trades": {}, "history": []}

    def _save_state(self):
        with open("state.json", "w") as f:
            json.dump(self.state, f, indent=2)

    # ==========================
    # DATA
    # ==========================
    def forecast_temp(self, lat, lon):
        try:
            r = self.session.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max",
                    "timezone": "auto",
                    "forecast_days": 1
                },
                timeout=15
            ).json()
            return r["daily"]["temperature_2m_max"][0]
        except:
            return None

    def sigma_temp(self, lat, lon):
        try:
            end = datetime.now() - timedelta(days=1)
            start = end - timedelta(days=30)
            r = self.session.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": end.strftime("%Y-%m-%d"),
                    "daily": "temperature_2m_max",
                    "timezone": "auto"
                },
                timeout=15
            ).json()
            temps = r["daily"]["temperature_2m_max"]
            mean = sum(temps) / len(temps)
            var = sum((t - mean) ** 2 for t in temps) / len(temps)
            return max(0.7, math.sqrt(var))
        except:
            return 1.5

    # ==========================
    # RESOLVER MERCADOS
    # ==========================
    def resolve_trades(self):
        hoy = datetime.now().strftime("%Y-%m-%d")
        activos = {}

        for m_id, t in self.state["open_trades"].items():
            if t["expiry"] < hoy:
                r = self.session.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params={
                        "latitude": t["lat"],
                        "longitude": t["lon"],
                        "start_date": t["expiry"],
                        "end_date": t["expiry"],
                        "daily": "temperature_2m_max",
                        "timezone": "auto"
                    }
                ).json()
                temp_real = r.get("daily", {}).get("temperature_2m_max", [None])[0]
                if temp_real is not None:
                    win_event = (temp_real > t["threshold"]) if t["op"] == ">" else (temp_real < t["threshold"])
                    success = (t["side"] == "YES" and win_event) or (t["side"] == "NO" and not win_event)
                    if success:
                        self.state["balance"] += t["stake"] + t["win_neto"]
                        print(f"💰 {t['city']} GANADO | +${t['win_neto']:.2f}")
                    else:
                        print(f"❌ {t['city']} PERDIDO | -${t['stake']:.2f}")
                else:
                    activos[m_id] = t
            else:
                activos[m_id] = t

        self.state["open_trades"] = activos

    # ==========================
    # ESCANEO + EARLY EXIT
    # ==========================
    def scan_markets(self):
        for city, cfg in CIUDADES.items():
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                break
            if any(t["city"] == city for t in self.state["open_trades"].values()):
                continue

            forecast = self.forecast_temp(cfg["lat"], cfg["lon"])
            sigma = self.sigma_temp(cfg["lat"], cfg["lon"])
            if forecast is None:
                continue

            markets = self.session.get(
                GAMMA_API,
                params={"active": "true", "query": city, "limit": 10},
                timeout=15
            ).json()

            for m in markets:
                try:
                    q = m.get("question", "").lower()
                    match = re.search(r"([-+]?\d*\.?\d+)", q)
                    if not match:
                        continue

                    threshold = float(match.group(1))
                    op = "<" if any(w in q for w in ["below", "under", "less"]) else ">"

                    prices = json.loads(m["outcomePrices"])
                    p_yes, p_no = float(prices[0]), float(prices[1])

                    z = (forecast - threshold) / sigma
                    prob_gt = 0.5 * (1 + math.erf(z / math.sqrt(2)))
                    prob_yes = prob_gt if op == ">" else 1 - prob_gt

                    edge_yes = prob_yes - p_yes
                    edge_no = (1 - prob_yes) - p_no

                    if edge_yes > edge_no:
                        side, prob, price, edge = "YES", prob_yes, p_yes, edge_yes
                    else:
                        side, prob, price, edge = "NO", 1 - prob_yes, p_no, edge_no

                    if edge > EDGE_THRESHOLD and float(m.get("liquidity", 0)) > 1000:
                        stake = round(self.state["balance"] * MAX_POSITION_PCT, 2)
                        self.state["balance"] -= stake

                        self.state["open_trades"][m["id"]] = {
                            "city": city,
                            "side": side,
                            "stake": stake,
                            "threshold": threshold,
                            "op": op,
                            "expiry": m["endDate"].split("T")[0],
                            "lat": cfg["lat"],
                            "lon": cfg["lon"],
                            "win_neto": round((stake / price - stake) * (1 - COMISION), 2)
                        }

                        print(f"🎯 {city} | {side} | Edge {edge:.1%}")
                        break
                except:
                    continue

    # ==========================
    # REPORTE
    # ==========================
    def report(self):
        self.state["history"].append(self.state["balance"])
        if len(self.state["history"]) > 5:
            plt.figure(figsize=(10, 5))
            plt.plot(self.state["history"], lw=2)
            plt.title(f"Equity Curve | Balance ${self.state['balance']:.2f}")
            plt.grid(alpha=0.3)
            plt.savefig("reports/equity.png")
            plt.close()

    # ==========================
    # RUN
    # ==========================
    def run(self):
        self.resolve_trades()
        self.scan_markets()
        self.report()
        self._save_state()


if __name__ == "__main__":
    WeatherTraderPro().run()
