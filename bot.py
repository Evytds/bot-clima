import requests
import json
import os
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================
VERSION = "9.0-CLIMATE-OPTIMIZED"
CAPITAL_INICIAL = 196.70

EDGE_BASE = 0.02
EDGE_LATE = 0.008
MAX_POSITION_PCT = 0.02
MAX_OPEN_TRADES = 12
COMISION = 0.02
MIN_LIQUIDITY = 400

CITIES = [
    "New York","Toronto","London","Seoul","Atlanta","Dallas",
    "Seattle","Buenos Aires","Chicago","Los Angeles","Tokyo","Sydney"
]

GAMMA_API = "https://gamma-api.polymarket.com/markets"

# ==========================
class ClimateTraderOptimized:
    def __init__(self):
        self.session = self._session()
        self.state = self._load_state()
        print(f"🚀 {VERSION} | Balance ${self.state['balance']:.2f}")

    def _session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[429,500,502,503,504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _load_state(self):
        if os.path.exists("state.json"):
            with open("state.json","r") as f:
                return json.load(f)
        return {"balance": CAPITAL_INICIAL, "open_trades": {}, "history": []}

    def _save_state(self):
        with open("state.json","w") as f:
            json.dump(self.state, f, indent=2)

    # ==========================
    def resolve_trades(self):
        activos = {}
        for m_id, t in self.state["open_trades"].items():
            try:
                r = self.session.get(f"{GAMMA_API}/{m_id}", timeout=10).json()
                if r.get("closed"):
                    win = "YES" if r.get("winnerOutcomeIndex") == "0" else "NO"
                    if t["side"] == win:
                        payout = t["stake"] + t["net"]
                        self.state["balance"] += payout
                        print(f"💰 WIN {t['city']} +${t['net']:.2f}")
                    else:
                        print(f"❌ LOSS {t['city']} -${t['stake']:.2f}")
                else:
                    activos[m_id] = t
            except:
                activos[m_id] = t
        self.state["open_trades"] = activos

    # ==========================
    def scan(self):
        for city in CITIES:
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                break

            try:
                markets = self.session.get(
                    GAMMA_API,
                    params={"active":"true","query":city,"limit":30},
                    timeout=15
                ).json()

                for m in markets:
                    if m["id"] in self.state["open_trades"]:
                        continue
                    if float(m.get("liquidity",0)) < MIN_LIQUIDITY:
                        continue

                    end = datetime.fromisoformat(m["endDate"].replace("Z",""))
                    hours_left = (end - datetime.utcnow()).total_seconds() / 3600
                    if hours_left > 48:
                        continue

                    prices = json.loads(m["outcomePrices"])
                    p_yes, p_no = float(prices[0]), float(prices[1])
                    if not (0.05 < p_yes < 0.95):
                        continue

                    edge = abs(1 - (p_yes + p_no))
                    edge_req = EDGE_LATE if hours_left < 24 else EDGE_BASE
                    if edge < edge_req:
                        continue

                    side = "YES" if p_yes < 0.5 else "NO"
                    price = p_yes if side == "YES" else p_no

                    stake_pct = MAX_POSITION_PCT * min(edge / EDGE_BASE, 1.2)
                    stake = round(self.state["balance"] * stake_pct, 2)
                    if stake < 0.5:
                        continue

                    self.state["balance"] -= stake
                    self.state["open_trades"][m["id"]] = {
                        "city": city,
                        "side": side,
                        "stake": stake,
                        "net": round((stake / price - stake) * (1 - COMISION), 2)
                    }

                    print(f"🎯 {city} {side} | Edge {edge*100:.2f}% | ${stake}")
                    break

            except Exception as e:
                print(f"⚠️ {city} error")

    def run(self):
        self.resolve_trades()
        self.scan()
        self.state["history"].append(round(self.state["balance"],2))
        self._save_state()
        print(f"✅ Balance ${self.state['balance']:.2f}")

# ==========================
if __name__ == "__main__":
    ClimateTraderOptimized().run()
