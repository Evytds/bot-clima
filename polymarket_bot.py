#!/usr/bin/env python3
"""
Polymarket Weather Trading Bot - Micro-Stake Edition
Optimizado para bankroll de $30 en Polymarket
"""

import argparse
import json
import logging
import math
import os
import re
import hashlib
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set
from functools import wraps
import threading

import dateparser
import requests
from requests.adapters import HTTPAdapter

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.constants import BUY
except ImportError:
    ClobClient = None
    OrderArgs = None
    BUY = None

# === CONFIGURACIÓN MICRO-STAKE $30 ===

CONFIG_PATH = Path("config") / "polymarket_auto.json"
STATE_DIR = Path("state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = STATE_DIR / "state.json"
STATE_BACKUP_PATH = STATE_DIR / "state.backup.json"
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# URLs Polymarket
POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com/markets"
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"

# APIs Clima
TOMORROWIO_URL = "https://api.tomorrow.io/v4/weather/forecast"
WEATHERBIT_URL = "https://api.weatherbit.io/v2.0/forecast/daily"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Locks thread-safety
state_lock = threading.Lock()

# === ESTRUCTURAS DE DATOS ===

@dataclass(frozen=True)
class MarketSnapshot:
    market_slug: str
    question: str
    city: str
    condition: str
    target_date: datetime
    liquidity: float
    volume_24h: float
    outcomes: Tuple[Dict[str, Any], ...]
    condition_id: str
    geo_group: Optional[str] = None

@dataclass(frozen=True)
class TradeDecision:
    market_slug: str
    city: str
    condition: str
    target_date: datetime
    forecast_avg: float
    forecast_high: float
    forecast_low: float
    outcome_label: str
    token_id: str
    side: str  # BUY o SELL
    fair_prob: float
    market_price: float
    edge: float
    stake: float
    ev_per_dollar: float
    provider_count: int
    correlation_penalty: float
    timestamp: datetime

# === LOGGING ===

def setup_logging():
    log_file = LOGS_DIR / f"bot_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# === UTILIDADES ===

def retry(max_tries=3, delay=1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_tries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == max_tries - 1:
                        raise
                    time.sleep(delay * (2 ** i))
        return wrapper
    return decorator

def atomic_write(path: Path, content: str):
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)
    except:
        if tmp.exists():
            tmp.unlink()
        raise

# === ESTADO ===

def load_state() -> Dict:
    with state_lock:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except:
                if STATE_BACKUP_PATH.exists():
                    return json.loads(STATE_BACKUP_PATH.read_text())
        return {
            "bankroll": 30.0,
            "daily_deposited": 30.0,
            "positions": [],
            "daily_pnl": 0.0,
            "trades_today": 0,
            "last_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            "total_trades": 0,
            "wins": 0,
            "losses": 0
        }

def save_state(state: Dict):
    with state_lock:
        if STATE_PATH.exists():
            STATE_PATH.replace(STATE_BACKUP_PATH)
        atomic_write(STATE_PATH, json.dumps(state, indent=2, default=str))

# === CONFIG ===

def load_config():
    """Config optimizada para $30 bankroll"""
    defaults = {
        # Bankroll inicial
        "initial_bankroll": 30.0,
        "trading_mode": "paper",
        
        # Ciudades con mercados líquidos en Polymarket
        "cities": [
            "New York", "NYC", "London", "Chicago", "Los Angeles",
            "Boston", "Miami", "Seattle", "Dallas", "Denver",
            "San Francisco", "Atlanta", "Toronto", "Tokyo"
        ],
        
        # Filtros de mercado - más permisivos para encontrar oportunidades
        "min_price": 0.05,      # No comprar outcomes caros
        "max_price": 0.95,      # No comprar outcomes baratos (vender en su lugar)
        "min_liquidity": 500,   # Mínimo para poder salir
        "min_volume_24h": 100,
        
        # Parámetros de edge - conservadores
        "min_edge_pct": 0.20,   # 20% mínimo de edge
        "forecast_confidence": 2.5,  # Grados de incertidumbre
        
        # Gestión de riesgo - ULTRA CONSERVADORA para $30
        "max_stake_per_trade": 5.0,      # Máximo $5 por trade (16.6% del bankroll)
        "max_daily_exposure": 15.0,      # Máximo $15 expuesto simultáneamente
        "max_trades_per_day": 3,         # Máximo 3 trades por día
        "min_bankroll_buffer": 10.0,     # Mantener $10 de buffer siempre
        
        # Kelly muy fraccionado
        "kelly_fraction": 0.10,          # 10% de Kelly full (prácticamente 1/20 Kelly)
        
        # Slippage
        "max_slippage": 0.01,            # 1% máximo
        
        # Grupos de correlación
        "correlation_groups": {
            "northeast": ["New York", "NYC", "Boston", "Philadelphia"],
            "west_coast": ["Los Angeles", "San Francisco", "Seattle"],
            "south": ["Miami", "Dallas", "Atlanta", "Houston"],
            "midwest": ["Chicago", "Denver", "Detroit"],
            "international": ["London", "Toronto", "Tokyo"]
        }
    }
    
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text())
            return {**defaults, **user}
        except:
            pass
    return defaults

# === FETCHERS POLYMARKET ===

@retry(max_tries=3)
def fetch_polymarket_markets(limit=500) -> List[Dict]:
    """Obtiene mercados activos de Polymarket Gamma API"""
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "limit": limit,
        "sort": "volume",
        "order": "desc"
    }
    
    resp = requests.get(POLYMARKET_GAMMA_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    markets = []
    for m in data if isinstance(data, list) else []:
        if not isinstance(m, dict):
            continue
        if m.get("closed", True) or m.get("archived", False):
            continue
        markets.append(m)
    
    logger.info(f"📊 {len(markets)} mercados activos en Polymarket")
    return markets

# === PARSING DE MERCADOS CLIMA ===

def parse_weather_market(market: Dict, config: Dict) -> Optional[MarketSnapshot]:
    """Extrae información de mercados climáticos de Polymarket"""
    question = market.get("question", "").lower()
    slug = market.get("slug", "")
    
    # Detectar ciudad
    city = None
    for c in config["cities"]:
        if c.lower() in question:
            city = c
            break
    
    if not city:
        return None
    
    # Detectar tipo de mercado
    condition = "unknown"
    if "temperature" in question or "high" in question or "low" in question:
        condition = "temperature"
    elif "rain" in question:
        condition = "rain"
    elif "snow" in question:
        condition = "snow"
    else:
        return None  # Solo nos interesa clima por ahora
    
    # Extraer fecha del título
    target_date = extract_date_from_question(question)
    if not target_date:
        target_date = datetime.now(timezone.utc) + timedelta(days=1)
    
    # Verificar que no cierra muy pronto (mínimo 6 horas)
    hours_to_close = (target_date - datetime.now(timezone.utc)).total_seconds() / 3600
    if hours_to_close < 6:
        return None
    
    # Determinar grupo de correlación
    geo_group = None
    for group, cities in config["correlation_groups"].items():
        if city in cities:
            geo_group = group
            break
    
    # Parsear outcomes
    outcomes = []
    for out in market.get("outcomes", []):
        price = float(out.get("price", 0))
        if config["min_price"] <= price <= config["max_price"]:
            outcomes.append({
                "label": out.get("name", out.get("label", "Unknown")),
                "price": price,
                "token_id": out.get("token_id", out.get("id", "")),
                "outcome_id": out.get("id", ""),
                "side": "BUY" if price < 0.5 else "SELL"
            })
    
    if len(outcomes) < 2:
        return None
    
    liquidity = float(market.get("liquidity", 0))
    volume = float(market.get("volume", 0))
    
    if liquidity < config["min_liquidity"] or volume < config["min_volume_24h"]:
        return None
    
    return MarketSnapshot(
        market_slug=slug,
        question=market.get("question", ""),
        city=city,
        condition=condition,
        target_date=target_date,
        liquidity=liquidity,
        volume_24h=volume,
        outcomes=tuple(outcomes),
        condition_id=market.get("conditionId", ""),
        geo_group=geo_group
    )

def extract_date_from_question(question: str) -> Optional[datetime]:
    """Extrae fecha de preguntas tipo 'Will it rain in NYC on January 15?'"""
    # Patrones comunes en Polymarket
    patterns = [
        r'on\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?)',
        r'for\s+([A-Za-z]+\s+\d{1,2})',
        r'(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            try:
                parsed = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
                if parsed:
                    return parsed.replace(tzinfo=timezone.utc)
            except:
                continue
    
    # Default: mañana
    return datetime.now(timezone.utc) + timedelta(days=1)

# === SISTEMA DE CLIMA ===

class WeatherService:
    """Servicio de clima con fallback entre providers"""
    
    def __init__(self, keys: Dict[str, str]):
        self.keys = keys
        self.cache = {}
    
    @retry(max_tries=2)
    def get_forecast(self, city: str, target_date: datetime) -> Optional[Dict]:
        """Obtiene forecast agregado de múltiples fuentes"""
        cache_key = f"{city}_{target_date.strftime('%Y%m%d')}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        forecasts = []
        
        # Intentar cada API en orden
        if self.keys.get("tomorrowio"):
            try:
                fc = self._tomorrowio(city, target_date)
                if fc: forecasts.append(("tomorrowio", fc))
            except Exception as e:
                logger.debug(f"Tomorrow.io falló: {e}")
        
        if self.keys.get("weatherbit"):
            try:
                fc = self._weatherbit(city, target_date)
                if fc: forecasts.append(("weatherbit", fc))
            except Exception as e:
                logger.debug(f"Weatherbit falló: {e}")
        
        if len(forecasts) == 0:
            return None
        
        # Promedio simple
        avg = mean([f["temp"] for _, f in forecasts])
        high = mean([f["high"] for _, f in forecasts])
        low = mean([f["low"] for _, f in forecasts])
        
        result = {
            "avg": avg,
            "high": high,
            "low": low,
            "providers": len(forecasts),
            "spread": max(f["temp"] for _, f in forecasts) - min(f["temp"] for _, f in forecasts)
        }
        
        self.cache[cache_key] = result
        return result
    
    def _tomorrowio(self, city: str, target_date: datetime) -> Optional[Dict]:
        # Coordenadas aproximadas (mejor usar geocoding en producción)
        coords = {
            "new york": (40.71, -74.01), "nyc": (40.71, -74.01),
            "london": (51.51, -0.13), "chicago": (41.88, -87.63),
            "los angeles": (34.05, -118.24), "boston": (42.36, -71.06),
            "miami": (25.76, -80.19), "seattle": (47.61, -122.33),
            "dallas": (32.78, -96.80), "denver": (39.74, -104.99),
            "san francisco": (37.77, -122.42), "atlanta": (33.75, -84.39),
            "toronto": (43.65, -79.38), "tokyo": (35.68, 139.69)
        }
        
        lat, lon = coords.get(city.lower(), (40.71, -74.01))
        
        params = {
            "location": f"{lat},{lon}",
            "apikey": self.keys["tomorrowio"],
            "fields": "temperature,temperatureMax,temperatureMin",
            "timesteps": "1d",
            "startTime": target_date.strftime("%Y-%m-%dT06:00:00Z"),
            "endTime": (target_date + timedelta(days=1)).strftime("%Y-%m-%dT06:00:00Z")
        }
        
        resp = requests.get(TOMORROWIO_URL, params=params, timeout=10)
        data = resp.json()
        
        timeline = data.get("timelines", {}).get("daily", [{}])[0]
        vals = timeline.get("values", {})
        
        return {
            "temp": vals.get("temperature", (vals.get("temperatureMax", 70) + vals.get("temperatureMin", 70)) / 2),
            "high": vals.get("temperatureMax", 75),
            "low": vals.get("temperatureMin", 65)
        }
    
    def _weatherbit(self, city: str, target_date: datetime) -> Optional[Dict]:
        params = {
            "city": city,
            "key": self.keys["weatherbit"],
            "days": 7
        }
        
        resp = requests.get(WEATHERBIT_URL, params=params, timeout=10)
        data = resp.json()
        
        for day in data.get("data", []):
            day_date = datetime.strptime(day["valid_date"], "%Y-%m-%d").date()
            if day_date == target_date.date():
                return {
                    "temp": day.get("temp", 70),
                    "high": day.get("max_temp", 75),
                    "low": day.get("min_temp", 65)
                }
        return None

# === MODELO DE PROBABILIDAD ===

def calculate_fair_prob(forecast: Dict, outcome_label: str, condition: str) -> Optional[float]:
    """Calcula probabilidad justa basada en forecast"""
    if condition != "temperature":
        return None  # TODO: implementar rain/snow
    
    # Extraer rango del label (ej: "Yes (70-75°F)" o "Yes, above 75°F")
    numbers = re.findall(r'\d+', outcome_label)
    if len(numbers) >= 2:
        low, high = int(numbers[0]), int(numbers[1])
    elif len(numbers) == 1:
        # Caso above/below
        num = int(numbers[0])
        if "above" in outcome_label.lower() or "over" in outcome_label.lower():
            low, high = num, 120
        else:
            low, high = -20, num
    else:
        return None
    
    # Modelo simple: probabilidad basada en distribución normal
    mean_temp = forecast["avg"]
    std_dev = 3.0  # Incertidumbre estándar de forecast a 24h
    
    # Z-scores
    z_low = (low - mean_temp) / std_dev
    z_high = (high - mean_temp) / std_dev
    
    # Probabilidad del rango
    prob = normal_cdf(z_high) - normal_cdf(z_low)
    
    # Ajuste por spread entre providers (mayor spread = más incertidumbre)
    if forecast.get("spread", 0) > 3:
        prob = 0.5 + (prob - 0.5) * 0.8  # Regresar hacia 50%
    
    return max(0.01, min(0.99, prob))

def normal_cdf(x: float) -> float:
    """Aproximación de distribución normal acumulada"""
    import math
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

# === KELLY MICRO-STAKE ===

def calculate_position_size(
    bankroll: float,
    available_exposure: float,
    fair_prob: float,
    market_price: float,
    edge: float,
    config: Dict
) -> float:
    """Calcula tamaño de posición para micro-bankroll"""
    
    # Si no hay edge positivo, no apostar
    if edge <= 0:
        return 0.0
    
    # Odds implícitas
    decimal_odds = 1 / market_price
    net_odds = decimal_odds - 1
    
    if net_odds <= 0:
        return 0.0
    
    # Kelly full: (p*(b+1) - 1) / b
    win_prob = fair_prob
    loss_prob = 1 - fair_prob
    kelly_full = (win_prob * net_odds - loss_prob) / net_odds
    
    if kelly_full <= 0:
        return 0.0
    
    # Fracción de Kelly muy pequeña para $30 bankroll
    kelly_frac = kelly_full * config["kelly_fraction"]
    
    # Stake base
    stake = bankroll * kelly_frac
    
    # Límites duros para $30
    stake = min(stake, config["max_stake_per_trade"])
    stake = min(stake, available_exposure)
    stake = max(stake, 1.0)  # Mínimo $1 en Polymarket
    
    # No dejar bankroll debajo del buffer
    if bankroll - stake < config["min_bankroll_buffer"]:
        stake = bankroll - config["min_bankroll_buffer"]
    
    if stake < 1.0:
        return 0.0
    
    return round(stake, 2)

# === CORRELACIÓN ===

def calculate_exposure_by_group(positions: List[Dict], config: Dict) -> Dict[str, float]:
    """Calcula exposición actual por grupo geográfico"""
    exposure = {}
    for pos in positions:
        group = pos.get("geo_group")
        if group:
            exposure[group] = exposure.get(group, 0) + pos.get("stake", 0)
    return exposure

# === EJECUCIÓN DE TRADES ===

class PolymarketExecutor:
    """Ejecutor de órdenes en Polymarket"""
    
    def __init__(self, mode: str, config: Dict):
        self.mode = mode
        self.config = config
        self.client = None
        
        if mode == "live":
            self._init_live_trading()
    
    def _init_live_trading(self):
        """Inicializa conexión live"""
        if not ClobClient:
            raise ImportError("Instala: pip install py-clob-client")
        
        key = os.getenv("POLYMARKET_PRIVATE_KEY")
        if not key:
            raise ValueError("POLYMARKET_PRIVATE_KEY no configurada")
        
        # Validación básica
        key_clean = key[2:] if key.startswith("0x") else key
        if len(key_clean) != 64:
            raise ValueError("Formato de clave privada inválido")
        
        self.client = ClobClient(
            host=POLYMARKET_CLOB_URL,
            chain_id=137,  # Polygon mainnet
            private_key=key
        )
        
        # Test conexión
        try:
            self.client.get_api_key()
            logger.info("✅ Conectado a Polymarket CLOB (LIVE)")
        except Exception as e:
            raise ConnectionError(f"No se pudo conectar a Polymarket: {e}")
    
    def execute(self, decision: TradeDecision) -> Tuple[bool, Dict]:
        """Ejecuta una decisión de trading"""
        if self.mode == "paper":
            return self._paper_trade(decision)
        else:
            return self._live_trade(decision)
    
    def _paper_trade(self, decision: TradeDecision) -> Tuple[bool, Dict]:
        """Simula trade en paper"""
        shares = decision.stake / decision.market_price
        
        result = {
            "mode": "paper",
            "market": decision.market_slug,
            "side": decision.side,
            "token_id": decision.token_id,
            "stake": decision.stake,
            "price": decision.market_price,
            "shares": round(shares, 4),
            "edge": decision.edge,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"📝 PAPER: {decision.city} | {decision.outcome_label} | "
                   f"${decision.stake:.2f} @ {decision.market_price:.3f} | "
                   f"Edge: {decision.edge:.1%}")
        
        return True, result
    
    def _live_trade(self, decision: TradeDecision) -> Tuple[bool, Dict]:
        """Ejecuta trade real en Polymarket"""
        try:
            # Calcular shares
            shares = decision.stake / decision.market_price
            
            # Usar limit order con pequeño buffer
            limit_price = decision.market_price * 1.005  # 0.5% de buffer
            limit_price = min(limit_price, 0.995)
            
            order_args = OrderArgs(
                token_id=decision.token_id,
                price=round(limit_price, 4),
                size=round(shares, 4),
                side=BUY if decision.side == "BUY" else SELL
            )
            
            logger.info(f"🚀 Enviando orden: {order_args}")
            
            resp = self.client.create_order(order_args)
            
            if resp.get("success") or "orderID" in str(resp):
                order_id = resp.get("orderID") or resp.get("id", "unknown")
                logger.info(f"✅ Orden ejecutada: {order_id}")
                
                return True, {
                    "mode": "live",
                    "order_id": order_id,
                    "status": "filled",
                    "response": resp
                }
            else:
                logger.error(f"❌ Orden rechazada: {resp}")
                return False, {"error": "rejected", "response": resp}
                
        except Exception as e:
            logger.exception(f"Error ejecutando orden: {e}")
            return False, {"error": str(e)}

# === LOOP PRINCIPAL ===

def run_bot():
    """Ejecución principal del bot de $30"""
    logger.info("=" * 50)
    logger.info("🤖 POLYMARKET WEATHER BOT - $30 EDITION")
    logger.info(f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info("=" * 50)
    
    # 1. Config y estado
    config = load_config()
    state = load_state()
    
    # Reset diario
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if state["last_date"] != today:
        logger.info("🌅 Nuevo día - reseteando contadores")
        state["daily_pnl"] = 0.0
        state["trades_today"] = 0
        state["last_date"] = today
    
    bankroll = state["bankroll"]
    mode = os.getenv("TRADING_MODE", config["trading_mode"]).lower()
    
    logger.info(f"💰 Bankroll: ${bankroll:.2f} | Mode: {mode.upper()}")
    logger.info(f"📊 Trades hoy: {state['trades_today']}/{config['max_trades_per_day']}")
    
    # 2. Circuit breakers
    if bankroll < config["min_bankroll_buffer"]:
        logger.error("🛑 Bankroll crítico - deteniendo")
        return
    
    if state["trades_today"] >= config["max_trades_per_day"]:
        logger.info("⏹️ Límite diario de trades alcanzado")
        return
    
    # 3. APIs de clima
    api_keys = {
        "tomorrowio": os.getenv("TOMORROWIO_API_KEY"),
        "weatherbit": os.getenv("WEATHERBIT_API_KEY")
    }
    
    if not any(api_keys.values()):
        logger.error("❌ Se requiere al menos una API de clima")
        return
    
    # 4. Inicializar servicios
    weather = WeatherService(api_keys)
    executor = PolymarketExecutor(mode, config)
    
    # 5. Fetch mercados
    try:
        markets = fetch_polymarket_markets(500)
    except Exception as e:
        logger.error(f"Error obteniendo mercados: {e}")
        return
    
    # 6. Filtrar mercados climáticos
    weather_markets = []
    for m in markets:
        parsed = parse_weather_market(m, config)
        if parsed:
            weather_markets.append(parsed)
    
    logger.info(f"🌤️ {len(weather_markets)} mercados climáticos encontrados")
    
    if not weather_markets:
        logger.info("No hay mercados para analizar")
        return
    
    # 7. Calcular exposición actual
    current_exposure = sum(p.get("stake", 0) for p in state["positions"] if p.get("status") == "open")
    exposure_by_group = calculate_exposure_by_group(state["positions"], config)
    available_exposure = config["max_daily_exposure"] - current_exposure
    
    logger.info(f"💵 Exposición actual: ${current_exposure:.2f} | "
               f"Disponible: ${available_exposure:.2f}")
    
    # 8. Analizar oportunidades
    opportunities = []
    
    for market in weather_markets:
        # Verificar correlación
        if market.geo_group:
            group_exp = exposure_by_group.get(market.geo_group, 0)
            if group_exp > config["max_daily_exposure"] * 0.5:
                continue  # Ya tenemos exposición en esta región
        
        # Obtener forecast
        forecast = weather.get_forecast(market.city, market.target_date)
        if not forecast:
            continue
        
        # Analizar cada outcome
        for outcome in market.outcomes:
            token_id = outcome.get("token_id", "")
            if not token_id:
                continue
            
            price = outcome["price"]
            side = "BUY" if price < 0.5 else "SELL"
            
            # Calcular prob justa
            fair_prob = calculate_fair_prob(forecast, outcome["label"], market.condition)
            if not fair_prob:
                continue
            
            # Calcular edge
            if side == "BUY":
                edge = (fair_prob - price) / price if price > 0 else 0
            else:  # SELL (short)
                edge = (price - fair_prob) / fair_prob if fair_prob > 0 else 0
            
            if edge < config["min_edge_pct"]:
                continue
            
            # Calcular stake
            stake = calculate_position_size(
                bankroll, available_exposure, fair_prob, price, edge, config
            )
            
            if stake <= 0:
                continue
            
            opportunities.append({
                "market": market,
                "outcome": outcome,
                "forecast": forecast,
                "fair_prob": fair_prob,
                "edge": edge,
                "stake": stake,
                "side": side
            })
    
    # 9. Seleccionar mejores oportunidades
    if not opportunities:
        logger.info("🔍 No se encontraron oportunidades con edge suficiente")
        return
    
    # Ordenar por edge y diversificar
    opportunities.sort(key=lambda x: x["edge"], reverse=True)
    
    # Tomar máximo 2 para no concentrar
    selected = opportunities[:2]
    
    logger.info(f"🎯 {len(selected)} oportunidades seleccionadas")
    
    # 10. Ejecutar trades
    executed = []
    for opp in selected:
        # Verificar límites
        if state["trades_today"] >= config["max_trades_per_day"]:
            break
        
        if current_exposure + opp["stake"] > config["max_daily_exposure"]:
            continue
        
        # Crear decisión
        decision = TradeDecision(
            market_slug=opp["market"].market_slug,
            city=opp["market"].city,
            condition=opp["market"].condition,
            target_date=opp["market"].target_date,
            forecast_avg=opp["forecast"]["avg"],
            forecast_high=opp["forecast"]["high"],
            forecast_low=opp["forecast"]["low"],
            outcome_label=opp["outcome"]["label"],
            token_id=opp["outcome"]["token_id"],
            side=opp["side"],
            fair_prob=opp["fair_prob"],
            market_price=opp["outcome"]["price"],
            edge=opp["edge"],
            stake=opp["stake"],
            ev_per_dollar=opp["edge"],
            provider_count=opp["forecast"]["providers"],
            correlation_penalty=1.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Ejecutar
        success, result = executor.execute(decision)
        
        if success:
            # Actualizar estado
            cost = decision.stake
            bankroll -= cost
            current_exposure += cost
            state["trades_today"] += 1
            state["total_trades"] += 1
            
            # Guardar posición
            position = {
                "market_slug": decision.market_slug,
                "token_id": decision.token_id,
                "city": decision.city,
                "geo_group": opp["market"].geo_group,
                "entry_price": decision.market_price,
                "stake": cost,
                "side": decision.side,
                "status": "open",
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "target_date": decision.target_date.isoformat()
            }
            state["positions"].append(position)
            executed.append(decision)
            
            logger.info(f"✅ Trade #{state['trades_today']} ejecutado: "
                       f"{decision.city} {decision.outcome_label} | "
                       f"${cost:.2f} | Edge: {decision.edge:.1%}")
    
    # 11. Guardar estado
    state["bankroll"] = round(bankroll, 2)
    save_state(state)
    
    # 12. Reporte final
    logger.info("=" * 50)
    logger.info(f"📈 SESIÓN FINALIZADA")
    logger.info(f"Trades ejecutados: {len(executed)}")
    logger.info(f"Bankroll: ${bankroll:.2f} ({bankroll - config['initial_bankroll']:+.2f})")
    logger.info(f"Exposición restante: ${config['max_daily_exposure'] - current_exposure:.2f}")
    logger.info("=" * 50)
    
    # Output JSON para piping
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trades": len(executed),
        "bankroll": bankroll,
        "exposure": current_exposure,
        "mode": mode
    }))

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Detenido por usuario")
    except Exception as e:
        logger.exception("Error fatal")
        raise
