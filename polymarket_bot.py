import argparse
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple

import dateparser
import requests

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.constants import BUY
except ImportError:
    ClobClient = None
    OrderArgs = None
    BUY = None

# Rutas en tu repo (persistentes con Render disk)
CONFIG_PATH = Path("config") / "polymarket_auto.json"
STATE_DIR = Path("state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = STATE_DIR / "state.json"

API_URL = "https://data-api.polymarket.com/activity"
POLYMARKET_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
TOMORROWIO_URL = "https://api.tomorrow.io/v4/weather/forecast"
WEATHERBIT_URL = "https://api.weatherbit.io/v2.0/forecast/daily"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"

@dataclass
class MarketSnapshot:
    market_slug: str
    question: str
    city: str
    liquidity: float
    outcomes: List[Dict[str, Any]]

@dataclass
class TradeDecision:
    market_slug: str
    city: str
    forecast_avg: float
    forecast_high: float
    forecast_low: float
    outcome_label: str
    token_id: str
    fair_prob: float
    market_price: float
    edge: float
    stake: float
    ev_per_dollar: float
    provider_count: int

# === Todas las funciones anteriores (fetch_activity hasta extract_market_date) ===
# (Copialas tal cual de tu versión anterior — están perfectas)

def decide_trade(
    market: MarketSnapshot,
    bankroll: float,
    forecast: Dict[str, float],
    deviation: float,
    min_edge_pct: float,
    min_stake: float,
    max_stake: float,
    max_bankroll_pct: float,
    provider_count: int,
    bin_width: float,
    half_kelly_factor: float,
) -> Optional[TradeDecision]:
    best = None
    mean = forecast["high"]
    for outcome in market.outcomes:
        fair_prob = probability_range(mean, deviation, outcome["low"], outcome["high"], bin_width=bin_width)
        market_price = outcome["price"]
        token_id = outcome.get("token_id", "")
        if market_price <= 0.0001 or market_price >= 0.9999 or not token_id:
            continue
        edge = (fair_prob - market_price) / market_price
        if best is None or edge > best["edge"]:
            best = {
                "label": outcome["label"],
                "token_id": token_id,
                "fair_prob": fair_prob,
                "market_price": market_price,
                "edge": edge,
            }

    if not best or best["edge"] < min_edge_pct:
        return None

    odds = (1 / best["market_price"]) - 1
    if odds <= 0:
        return None
    kelly_f = best["edge"] / odds
    stake = bankroll * kelly_f * half_kelly_factor

    stake = max(stake, min_stake)
    stake = min(stake, max_stake, bankroll * max_bankroll_pct)
    stake = round(stake, 2)

    if stake < min_stake:
        logging.info(f"Stake ${stake:.2f} < $1.00 → skip")
        return None

    return TradeDecision(
        market_slug=market.market_slug,
        city=market.city,
        forecast_avg=forecast["avg"],
        forecast_high=forecast["high"],
        forecast_low=forecast["low"],
        outcome_label=best["label"],
        token_id=best["token_id"],
        fair_prob=best["fair_prob"],
        market_price=best["market_price"],
        edge=best["edge"],
        stake=stake,
        ev_per_dollar=best["edge"],
        provider_count=provider_count,
    )

def run_autonomous_bot() -> None:
    # Default config
    default_config = {
        "bankroll": 30.0,
        "trading_mode": "paper",
        "cities": ["New York","NYC","London","Seoul","Dallas","Atlanta","Toronto","Chicago","Los Angeles","Paris","Tokyo","Wellington","Miami","Boston","Houston","San Francisco"],
        "min_price": 0.001,
        "max_price": 0.10,
        "min_liquidity": 50.0,
        "min_edge_pct": 0.12,
        "deviation": 3.5,
        "bin_width": 2.0,
        "half_kelly_factor": 0.5,
        "min_stake": 1.0,
        "max_stake": 15.0,
        "max_bankroll_pct_per_trade": 0.20,
        "markets_limit": 200,
    }

    config = default_config
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = {**default_config, **config}

    # Env vars override
    config["trading_mode"] = os.getenv("TRADING_MODE", config["trading_mode"])

    state = {"bankroll": config["bankroll"], "positions": []}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    bankroll = float(state.get("bankroll", config["bankroll"]))

    api_keys = {
        "tomorrowio": os.getenv("TOMORROWIO_API_KEY"),
        "weatherbit": os.getenv("WEATHERBIT_API_KEY"),
        "openweather": os.getenv("OPENWEATHER_API_KEY"),
    }
    if not any(api_keys.values()):
        logging.error("Falta API key de clima")
        return

    trading_mode = config["trading_mode"].lower()
    clob_client = None
    if trading_mode == "live":
        if not ClobClient:
            logging.error("Instala py-clob-client")
            return
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        if not private_key:
            logging.error("Private key requerida")
            return
        clob_client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=137,
            private_key=private_key,
        )
        logging.info("LIVE TRADING ON")

    markets = fetch_polymarket_markets(POLYMARKET_MARKETS_URL, config["markets_limit"])
    weather_markets = filter_weather_markets(markets, config["cities"], config["min_price"], config["max_price"], config["min_liquidity"])

    decisions = []
    for market in weather_markets:
        # ... (forecasts y decision igual)

        if decision:
            shares = decision.stake / decision.market_price
            logging.info(f"{trading_mode.upper()}: ${decision.stake:.2f} en {decision.city} {decision.outcome_label}")

            if trading_mode == "live":
                try:
                    order_args = OrderArgs(token_id=decision.token_id, price=decision.market_price, size=shares, side=BUY)
                    response = clob_client.create_order(order_args)
                    if response.get("status") == "success":
                        bankroll -= decision.stake
                    else:
                        logging.error(f"Orden falló: {response}")
                except Exception as e:
                    logging.error(f"Error: {e}")
            else:
                bankroll -= decision.stake

            state["positions"].append({ /* datos */ })
            decisions.append(decision)

    state["bankroll"] = round(bankroll, 2)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if decisions:
        print("✅ Decisiones hoy")
    else:
        print("ℹ️ No edges")

if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    run_autonomous_bot()
