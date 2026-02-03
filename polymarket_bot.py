import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

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
    fair_prob: float
    market_price: float
    edge: float
    outcome: str
    stake: float
    ev_per_dollar: float
    provider_count: int


def fetch_activity(wallet: str, limit: int) -> List[Dict[str, Any]]:
    response = requests.get(
        API_URL,
        params={
            "user": wallet,
            "limit": limit,
            "sortBy": "timestamp",
            "sortDirection": "DESC",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("API response was not a list")
    return payload


def normalize_activity(activity: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for item in activity:
        timestamp_ms = int(item.get("timestamp", 0))
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        normalized.append(
            {
                "timestamp": timestamp,
                "market": item.get("marketSlug") or "Desconocido",
                "type": item.get("type") or "N/A",
                "side": item.get("outcome") or "N/A",
                "size": float(item.get("size", 0) or 0),
                "price": float(item.get("price", 0) or 0),
                "tx": item.get("txHash") or "",
            }
        )
    return normalized


def summarize(activity: List[Dict[str, Any]]) -> Dict[str, Any]:
    sizes = [item["size"] for item in activity]
    markets = sorted({item["market"] for item in activity})
    latest = max((item["timestamp"] for item in activity), default=None)

    return {
        "total_actions": len(activity),
        "unique_markets": len(markets),
        "average_size": mean(sizes) if sizes else 0,
        "total_volume": sum(sizes),
        "latest_action": latest.isoformat() if latest else "N/A",
        "markets": markets,
    }


def build_time_series(activity: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    ordered = sorted(activity, key=lambda item: item["timestamp"])
    labels = []
    cumulative = []
    running = 0.0
    for item in ordered:
        running += item["size"]
        labels.append(item["timestamp"].strftime("%Y-%m-%d %H:%M"))
        cumulative.append(round(running, 4))
    return {"labels": labels, "data": cumulative}


def render_html(
    wallet: str,
    summary: Dict[str, Any],
    activity: List[Dict[str, Any]],
    series: Dict[str, List[Any]],
) -> str:
    rows = "\n".join(
        """
            <tr>
                <td>{timestamp}</td>
                <td>{market}</td>
                <td>{type}</td>
                <td>{side}</td>
                <td>${price:.4f}</td>
                <td>{size:.4f}</td>
            </tr>
        """.format(
            timestamp=item["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            market=item["market"],
            type=item["type"],
            side=item["side"],
            price=item["price"],
            size=item["size"],
        )
        for item in activity[:15]
    )

    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background: #0f172a; color: #e2e8f0; font-family: "Inter", sans-serif; margin: 0; padding: 32px; }}
        .container {{ max-width: 960px; margin: auto; background: #1e293b; padding: 28px; border-radius: 20px; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.6); }}
        h1 {{ margin-top: 0; color: #f8fafc; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 20px 0; }}
        .card {{ background: #111827; border-radius: 16px; padding: 16px; }}
        .label {{ color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; }}
        .value {{ font-size: 1.4rem; color: #38bdf8; font-weight: 600; margin-top: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 0.9rem; }}
        th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #334155; }}
        th {{ color: #cbd5f5; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Bot de seguimiento Polymarket</h1>
        <p>Wallet monitoreada: <strong>{wallet}</strong></p>
        <div class="summary">
            <div class="card">
                <div class="label">Total de movimientos</div>
                <div class="value">{summary["total_actions"]}</div>
            </div>
            <div class="card">
                <div class="label">Mercados únicos</div>
                <div class="value">{summary["unique_markets"]}</div>
            </div>
            <div class="card">
                <div class="label">Volumen total</div>
                <div class="value">{summary["total_volume"]:.2f}</div>
            </div>
            <div class="card">
                <div class="label">Apuesta promedio</div>
                <div class="value">{summary["average_size"]:.2f}</div>
            </div>
        </div>
        <canvas id="activityChart" height="120"></canvas>
        <table>
            <thead>
                <tr>
                    <th>Fecha</th>
                    <th>Mercado</th>
                    <th>Tipo</th>
                    <th>Lado</th>
                    <th>Precio</th>
                    <th>Tamaño</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    <script>
        const labels = {json.dumps(series["labels"])};
        const data = {json.dumps(series["data"])};

        new Chart(document.getElementById('activityChart'), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Volumen acumulado',
                    data: data,
                    borderColor: '#38bdf8',
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 3,
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }}
            }}
        }});
    </script>
</body>
</html>
"""

def fetch_polymarket_markets(api_url: str, limit: int) -> List[Dict[str, Any]]:
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
    }
    response = requests.get(api_url, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        markets = payload.get("markets") or payload.get("data") or []
    else:
        markets = payload
    if not isinstance(markets, list):
        raise ValueError("Respuesta inesperada del API de Polymarket.")
    return markets


def extract_yes_price(market: Dict[str, Any]) -> Optional[float]:
    for key in ("yesPrice", "bestAsk", "priceYes", "lastPriceYes"):
        value = market.get(key)
        if value is not None:
            return float(value)

    outcomes = market.get("outcomes")
    if isinstance(outcomes, list):
        for outcome in outcomes:
            if str(outcome.get("outcome", "")).lower() == "yes":
                price = outcome.get("price")
                if price is not None:
                    return float(price)
    return None


def extract_liquidity(market: Dict[str, Any]) -> float:
    for key in ("liquidity", "volume", "liquidityUsd", "volumeUsd"):
        value = market.get(key)
        if value is not None:
            return float(value)
    return 0.0


def parse_outcome_range(label: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    text = label.lower()
    text = re.sub(r"[°\\s]*[cf]", "", text)
    text = text.replace(" or above", " or higher").replace(" or below", " or lower")

    if "or higher" in text:
        match = re.search(r"(-?\\d+(?:\\.\\d+)?)", text)
        if match:
            return float(match.group(1)), None
        return None

    if "or lower" in text or "below" in text:
        match = re.search(r"(-?\\d+(?:\\.\\d+)?)", text)
        if match:
            return None, float(match.group(1))
        return None

    match = re.search(r"(-?\\d+(?:\\.\\d+)?)\\s*(?:-|–|to)\\s*(-?\\d+(?:\\.\\d+)?)", text)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None


def parse_market_outcomes(market: Dict[str, Any]) -> List[Dict[str, Any]]:
    outcomes = market.get("outcomes")
    parsed = []
    if not isinstance(outcomes, list):
        return parsed
    for outcome in outcomes:
        label = outcome.get("outcome") or outcome.get("label") or ""
        price = outcome.get("price")
        if label and price is not None:
            range_info = parse_outcome_range(str(label))
            if range_info:
                low, high = range_info
                parsed.append(
                    {
                        "label": str(label),
                        "price": float(price),
                        "low": low,
                        "high": high,
                    }
                )
    return parsed


def match_city(text: str, cities: Iterable[str]) -> Optional[str]:
    text_lower = text.lower()
    for city in cities:
        if city.lower() in text_lower:
            return city
    return None


def filter_weather_markets(
    markets: List[Dict[str, Any]],
    cities: List[str],
    min_price: float,
    max_price: float,
    min_liquidity: float,
) -> List[MarketSnapshot]:
    filtered = []
    for market in markets:
        question = market.get("question") or market.get("title") or market.get("marketSlug") or ""
        question_lower = question.lower()
        if "highest temperature" not in question_lower and "high temperature" not in question_lower:
            continue
        city = match_city(question, cities)
        if not city:
            continue
        liquidity = extract_liquidity(market)
        if liquidity < min_liquidity:
            continue
        outcomes = parse_market_outcomes(market)
        outcomes = [
            outcome
            for outcome in outcomes
            if min_price <= outcome["price"] <= max_price
        ]
        if not outcomes:
            continue
        market_slug = market.get("marketSlug") or market.get("slug") or question
        filtered.append(
            MarketSnapshot(
                market_slug=str(market_slug),
                question=str(question),
                city=city,
                liquidity=liquidity,
                outcomes=outcomes,
            )
        )
    return filtered


def fetch_forecast_tomorrowio(city: str, api_key: str) -> Dict[str, float]:
    response = requests.get(
        TOMORROWIO_URL,
        params={
            "location": city,
            "timesteps": "1d",
            "units": "imperial",
            "apikey": api_key,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    timelines = payload.get("timelines", {}).get("daily", [])
    if not timelines:
        raise ValueError(f"No forecast diario para {city}")
    values = timelines[0].get("values", {})
    high = values.get("temperatureMax")
    low = values.get("temperatureMin")
    avg = values.get("temperatureAvg")
    if high is None or low is None or avg is None:
        raise ValueError(f"Forecast incompleto para {city}")
    return {"high": float(high), "low": float(low), "avg": float(avg)}


def fetch_forecast_weatherbit(city: str, api_key: str) -> Dict[str, float]:
    response = requests.get(
        WEATHERBIT_URL,
        params={
            "city": city,
            "days": 1,
            "units": "I",
            "key": api_key,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", [])
    if not data:
        raise ValueError(f"No forecast diario para {city} en Weatherbit")
    entry = data[0]
    high = entry.get("max_temp")
    low = entry.get("min_temp")
    avg = entry.get("temp")
    if high is None or low is None or avg is None:
        raise ValueError(f"Forecast incompleto para {city} en Weatherbit")
    return {"high": float(high), "low": float(low), "avg": float(avg)}


def fetch_forecast_openweather(city: str, api_key: str) -> Dict[str, float]:
    response = requests.get(
        OPENWEATHER_URL,
        params={
            "q": city,
            "appid": api_key,
            "units": "imperial",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("list", [])
    if not entries:
        raise ValueError(f"No forecast horario para {city} en OpenWeather")
    temps = [entry.get("main", {}).get("temp") for entry in entries if entry.get("main")]
    temps = [temp for temp in temps if temp is not None]
    if not temps:
        raise ValueError(f"Forecast incompleto para {city} en OpenWeather")
    return {"high": float(max(temps)), "low": float(min(temps)), "avg": float(sum(temps) / len(temps))}


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def probability_range(
    mean: float,
    deviation: float,
    low: Optional[float],
    high: Optional[float],
    bin_width: float = 1.0,
) -> float:
    if low is None and high is not None:
        z = (high + bin_width - mean) / deviation
        return normal_cdf(z)
    if high is None and low is not None:
        z = (low - mean) / deviation
        return 1 - normal_cdf(z)
    if low is not None and high is not None:
        upper = (high + bin_width - mean) / deviation
        lower = (low - mean) / deviation
        return max(normal_cdf(upper) - normal_cdf(lower), 0.0)
    return 0.0


def consensus_forecast(forecasts: List[Dict[str, float]]) -> Dict[str, float]:
    highs = [entry["high"] for entry in forecasts]
    lows = [entry["low"] for entry in forecasts]
    avgs = [entry["avg"] for entry in forecasts]
    return {
        "high": sum(highs) / len(highs),
        "low": sum(lows) / len(lows),
        "avg": sum(avgs) / len(avgs),
    }


def decide_trade(
    market: MarketSnapshot,
    bankroll: float,
    forecast: Dict[str, float],
    deviation: float,
    min_edge_pct: float,
    stake_pct: float,
    max_stake: float,
    provider_count: int,
) -> Optional[TradeDecision]:
    best = None
    mean = forecast["high"]
    for outcome in market.outcomes:
        fair_prob = probability_range(mean, deviation, outcome["low"], outcome["high"])
        market_price = outcome["price"]
        if market_price <= 0:
            continue
        edge = (fair_prob - market_price) / market_price
        if best is None or edge > best["edge"]:
            best = {
                "label": outcome["label"],
                "fair_prob": fair_prob,
                "market_price": market_price,
                "edge": edge,
            }

    if not best or best["edge"] < min_edge_pct:
        return None

    stake = min(bankroll * stake_pct, max_stake, bankroll)
    return TradeDecision(
        market_slug=market.market_slug,
        city=market.city,
        forecast_avg=forecast["avg"],
        forecast_high=forecast["high"],
        forecast_low=forecast["low"],
        outcome_label=best["label"],
        fair_prob=best["fair_prob"],
        market_price=best["market_price"],
        edge=best["edge"],
        outcome="BUY",
        stake=round(stake, 2),
        ev_per_dollar=best["edge"],
        provider_count=provider_count,
    )


def run_autonomous_bot(config_path: Path, state_path: Path) -> None:
    config = load_json(
        config_path,
        {
            "bankroll": 100.0,
            "cities": ["London", "New York", "Seoul"],
            "min_price": 0.001,
            "max_price": 0.10,
            "min_liquidity": 50.0,
            "min_edge_pct": 0.2,
            "deviation": 3.5,
            "stake_pct": 0.05,
            "max_stake": 10.0,
            "markets_limit": 200,
            "note": "Configura claves TOMORROWIO_API_KEY, WEATHERBIT_API_KEY u OPENWEATHER_API_KEY.",
        },
    )
    state = load_json(state_path, {"bankroll": config.get("bankroll", 100.0), "positions": []})
    bankroll = float(state.get("bankroll", config.get("bankroll", 100.0)))

    api_keys = {
        "tomorrowio": os.getenv("TOMORROWIO_API_KEY"),
        "weatherbit": os.getenv("WEATHERBIT_API_KEY"),
        "openweather": os.getenv("OPENWEATHER_API_KEY"),
    }
    if not any(api_keys.values()):
        raise SystemExit("Falta al menos una API key de clima (Tomorrow.io, Weatherbit u OpenWeather).")

    markets = fetch_polymarket_markets(
        config.get("polymarket_markets_url", POLYMARKET_MARKETS_URL),
        int(config.get("markets_limit", 200)),
    )
    weather_markets = filter_weather_markets(
        markets,
        config.get("cities", ["London", "New York", "Seoul"]),
        float(config.get("min_price", 0.001)),
        float(config.get("max_price", 0.10)),
        float(config.get("min_liquidity", 50.0)),
    )

    decisions = []
    for market in weather_markets:
        forecasts = []
        if api_keys["tomorrowio"]:
            forecasts.append(fetch_forecast_tomorrowio(market.city, api_keys["tomorrowio"]))
        if api_keys["weatherbit"]:
            forecasts.append(fetch_forecast_weatherbit(market.city, api_keys["weatherbit"]))
        if api_keys["openweather"]:
            forecasts.append(fetch_forecast_openweather(market.city, api_keys["openweather"]))
        if not forecasts:
            continue
        forecast = consensus_forecast(forecasts)
        decision = decide_trade(
            market,
            bankroll,
            forecast,
            float(config.get("deviation", 3.5)),
            float(config.get("min_edge_pct", 0.2)),
            float(config.get("stake_pct", 0.05)),
            float(config.get("max_stake", 10.0)),
            len(forecasts),
        )
        if decision:
            bankroll -= decision.stake
            state["positions"].append(
                {
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    "city": decision.city,
                    "market_slug": decision.market_slug,
                    "forecast_avg": decision.forecast_avg,
                    "forecast_high": decision.forecast_high,
                    "forecast_low": decision.forecast_low,
                    "outcome_label": decision.outcome_label,
                    "fair_prob": decision.fair_prob,
                    "market_price": decision.market_price,
                    "edge": decision.edge,
                    "outcome": decision.outcome,
                    "stake": decision.stake,
                    "ev_per_dollar": decision.ev_per_dollar,
                    "provider_count": decision.provider_count,
                    "mode": "paper",
                }
            )
            decisions.append(decision)

    state["bankroll"] = round(bankroll, 2)
    save_json(state_path, state)

    if not decisions:
        print("ℹ️ No se encontraron oportunidades con el umbral actual.")
        return

    print("✅ Decisiones tomadas (modo simulación/paper):")
    for decision in decisions:
        print(
            f"- {decision.city} | {decision.market_slug} | "
            f"{decision.outcome_label} | high {decision.forecast_high:.1f} → {decision.outcome} "
            f"edge {decision.edge:.2%} EV {decision.ev_per_dollar:+.3f} "
            f"fuentes {decision.provider_count} con ${decision.stake:.2f}"
        )
    print(f"💼 Bankroll restante: ${state['bankroll']:.2f}")


def run_report(wallet: str, limit: int, output: Path, json_path: Path) -> None:
    activity = normalize_activity(fetch_activity(wallet, limit))
    if not activity:
        raise SystemExit("No se encontró actividad reciente para esa wallet.")

    summary = summarize(activity)
    series = build_time_series(activity)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(wallet, summary, activity, series), encoding="utf-8")

    json_payload = {
        "wallet": wallet,
        "summary": summary,
        "activity": [
            {
                "timestamp": item["timestamp"].isoformat(),
                "market": item["market"],
                "type": item["type"],
                "side": item["side"],
                "size": item["size"],
                "price": item["price"],
                "tx": item["tx"],
            }
            for item in activity
        ],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Reporte HTML generado en: {output}")
    print(f"✅ Reporte JSON generado en: {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bot Polymarket: reporte de actividad o modo autónomo (paper trading)."
    )
    parser.add_argument("--mode", choices=["report", "auto"], default="report")
    parser.add_argument("--wallet", help="Wallet de Polymarket a monitorear (modo report)")
    parser.add_argument("--limit", type=int, default=100, help="Número de operaciones a recuperar")
    parser.add_argument(
        "--output",
        default="reports/polymarket_report.html",
        help="Ruta del HTML generado",
    )
    parser.add_argument(
        "--json",
        default="reports/polymarket_report.json",
        help="Ruta del JSON generado",
    )
    parser.add_argument(
        "--config",
        default="config/polymarket_auto.json",
        help="Config JSON para modo autónomo (paper trading)",
    )
    parser.add_argument(
        "--state",
        default="state/polymarket_auto_state.json",
        help="Estado JSON para modo autónomo (paper trading)",
    )
    args = parser.parse_args()

    if args.mode == "report":
        if not args.wallet:
            raise SystemExit("Debes indicar --wallet en modo report.")
        run_report(args.wallet, args.limit, Path(args.output), Path(args.json))
        return

    run_autonomous_bot(Path(args.config), Path(args.state))


if __name__ == "__main__":
    main()
