import requests
import json
import os
import time
import re
import logging
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================
# CONFIGURACIÓN GENERAL - BOT METEO MEJORADO CON PRONÓSTICOS Y ALERTS
# ==========================
VERSION = "10.0-FULL-INTEGRATED-METEO-BOT"

CAPITAL_INICIAL = 40.00

EDGE_MIN = 0.0005
MAX_POSITION_PCT_BASE = 0.05
MAX_POSITION_PCT_MAX = 0.10
MAX_OPEN_TRADES = 15
COMISION = 0.001
MIN_LIQUIDITY = 50

GAMMA_API = "https://gamma-api.polymarket.com/markets"

# OpenWeatherMap (gratis: openweathermap.org/api)
OPENWEATHER_API_KEY = "your_openweather_api_key_here"  # ¡REEMPLAZA CON TU CLAVE GRATIS!
OPENWEATHER_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"

# Email alerts (Gmail: usa App Password en https://myaccount.google.com/apppasswords)
EMAIL_SENDER = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_RECIPIENT = "your_email@gmail.com"
ENABLE_EMAIL_ALERTS = False  # Cambia a True y configura para alerts

# Opciones avanzadas
ENABLE_FORECAST = True  # Usa pronósticos para filtrar trades
ENABLE_DIVERSIFICATION = False  # Escanea politics/crypto si True
BACKTEST_MODE = False  # Futuro: simula histórico (por ahora False)
CYCLE_SLEEP = 300  # 5 min entre ciclos en prod (ajusta)

# Ciudades priorizadas (con mapping para OpenWeather)
CITIES = {
    "New York": "New York,US",
    "New York City": "New York,US",
    "Toronto": "Toronto,CA",
    "London": "London,UK",
    "Seattle": "Seattle,US",
    "Dallas": "Dallas,US",
    "Atlanta": "Atlanta,US",
    "Chicago": "Chicago,US",
    "Los Angeles": "Los Angeles,US",
    "Buenos Aires": "Buenos Aires,AR",
    "Seoul": "Seoul,KR",
    "Tokyo": "Tokyo,JP",
    "Sydney": "Sydney,AU",
    "Boston": "Boston,US",
    "Miami": "Miami,US",
    "San Francisco": "San Francisco,US"
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# ==========================
# BOT PRINCIPAL
# ==========================
class PolyWeatherBot:
    def __init__(self):
        self.session = self._setup_session()
        self.state = self._load_state()
        self.initial_balance = self.state.get('initial_balance', CAPITAL_INICIAL)
        logger.info(f"🚀 {VERSION} iniciado | Balance: ${self.state['balance']:.2f} | Inicial: ${self.initial_balance:.2f}")

    def _setup_session(self):
        s = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _load_state(self):
        if os.path.exists("state.json"):
            try:
                with open("state.json", "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"state.json corrupto ({e}) — reiniciando")
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
        try:
            with open("state.json", "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando state: {e}")

    def _send_email_alert(self, subject, body):
        if not ENABLE_EMAIL_ALERTS:
            return
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_SENDER
            msg['To'] = EMAIL_RECIPIENT
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
            server.quit()
            logger.info("📧 Email alert enviado")
        except Exception as e:
            logger.error(f"Error email: {e}")

    def _get_weather_forecast(self, city_ow):
        """Obtiene temp max pronosticada para mañana (proxy para daily high) en °F"""
        if not ENABLE_FORECAST or not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "your_openweather_api_key_here":
            logger.warning("Forecast deshabilitado (sin API key)")
            return None
        try:
            # Pronóstico 5 días, toma max de mañana ~12-15 UTC
            tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
            url = f"{OPENWEATHER_FORECAST}?q={city_ow}&appid={OPENWEATHER_API_KEY}&units=imperial&cnt=8"
            r = self.session.get(url, timeout=10).json()
            highs = [f['main']['temp_max'] for f in r['list'] if tomorrow in f['dt_txt']]
            return max(highs) if highs else None
        except Exception as e:
            logger.warning(f"Error forecast {city_ow}: {e}")
            return None

    def parse_temp_expectation(self, question):
        """Parsea expectativa de temp del mercado. Retorna (expected_temp/range_low, range_high, unit) o None"""
        q = question.lower()
        # Detecta °F / °C
        unit = 'f' if '°f' in q or 'fahrenheit' in q else 'c' if '°c' in q or 'celsius' in q else 'f'  # Default °F
        # Extrae números (temps como 42, 42-43, above 50)
        nums = re.findall(r'(\d+(?:\.\d+)?)', q)
        if not nums:
            return None
        exp_low, exp_high = float(nums[0]), float(nums[0])
        if len(nums) > 1:
            exp_high = float(nums[1])
        # Clasifica: exact, range estrecha (<5°), above/below
        is_exact_or_narrow = exp_high - exp_low < 5 or 'exact' in q or 'between' in q
        is_above = 'above' in q or 'exceed' in q
        is_below = 'below' in q
        return {
            "low": exp_low,
            "high": exp_high,
            "unit": unit,
            "is_narrow": is_exact_or_narrow,
            "is_above": is_above,
            "is_below": is_below
        }

    def has_forecast_edge(self, question, city_ow, forecast_temp):
        """Decide si apostar NO basado en forecast vs expectativa"""
        if not forecast_temp:
            return False
        temp_exp = self.parse_temp_expectation(question)
        if not temp_exp:
            return False
        exp_low, exp_high = temp_exp['low'], temp_exp['high']
        # Si narrow range y forecast fuera: fuerte NO
        if temp_exp['is_narrow'] and not (exp_low <= forecast_temp <= exp_high):
            return True
        # Above: si forecast < low
        if temp_exp['is_above'] and forecast_temp < exp_low:
            return True
        # Below: si forecast > high
        if temp_exp['is_below'] and forecast_temp > exp_high:
            return True
        return False

    def is_weather_market(self, question):
        q = question.lower()
        keywords = [
            "temperature", "temp", "degree", "°", "high", "max",
            "above", "below", "reach", "exceed", "between", "exact"
        ]
        return any(k in q for k in keywords)

    def resolve_trades(self):
        if not self.state["open_trades"]:
            return
        active = {}
        resolved = []
        for mid, trade in self.state["open_trades"].items():
            try:
                r = self.session.get(f"{GAMMA_API}/{mid}", timeout=10).json()
                if r.get("closed"):
                    winner_idx = r.get("winnerOutcomeIndex")
                    winner_side = "YES" if winner_idx == 0 else "NO"
                    self.state["total_trades"] += 1
                    if trade["side"] == winner_side:
                        win_amount = trade["stake"] / trade["price"]
                        profit = win_amount * (1 - COMISION) - trade["stake"]
                        self.state["balance"] += profit
                        self.state["wins"] += 1
                        msg = f"💰 WIN {trade['city']}: +${profit:.2f}"
                        logger.info(msg)
                        resolved.append(msg)
                    else:
                        self.state["losses"] += 1
                        msg = f"❌ LOSS {trade['city']}: -${trade['stake']:.2f}"
                        logger.info(msg)
                        resolved.append(msg)
                else:
                    active[mid] = trade
            except Exception as e:
                logger.warning(f"Error resolve {mid}: {e}")
                active[mid] = trade
        self.state["open_trades"] = active
        if resolved:
            win_rate = self.state["wins"] / self.state["total_trades"] * 100 if self.state["total_trades"] else 0
            roi = (self.state["balance"] - self.initial_balance) / self.initial_balance * 100
            summary = f"Resueltos: {len(resolved)} | Win Rate: {win_rate:.1f}% | ROI: {roi:.1f}% | Balance: ${self.state['balance']:.2f}"
            logger.info(summary)
            self._send_email_alert("PolyWeatherBot: Trades Resueltos", "\n".join(resolved) + "\n" + summary)

    def scan_markets(self):
        logger.info("🌦️ Escaneando mercados...")
        scanned = 0
        for city, city_ow in CITIES.items():
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                logger.warning("Límite trades abiertos")
                break
            forecast_temp = self._get_weather_forecast(city_ow)
            try:
                params = {"active": "true", "query": city, "limit": 30}
                markets = self.session.get(GAMMA_API, params=params, timeout=15).json()
                for m in markets:
                    mid = m["id"]
                    if mid in self.state["open_trades"]:
                        continue
                    if ENABLE_DIVERSIFICATION and not self.is_weather_market(m.get("question", "")):
                        continue  # Solo weather por default
                    question = m["question"]
                    if not self.is_weather_market(question):
                        continue
                    liquidity = float(m.get("liquidity", 0))
                    if liquidity < MIN_LIQUIDITY:
                        continue
                    prices = json.loads(m.get("outcomePrices", "[]"))
                    if len(prices) != 2:
                        continue
                    p_yes, p_no = prices
                    if not (0.01 < p_yes < 0.99 and 0.01 < p_no < 0.99):
                        continue
                    edge = abs(1 - (p_yes + p_no))
                    if edge < EDGE_MIN:
                        continue

                    # Filtro forecast: solo NO si mismatch
                    forecast_good_for_no = self.has_forecast_edge(question, city_ow, forecast_temp)
                    side, price = None, None
                    if forecast_good_for_no and p_no < 0.60:
                        side, price = "NO", p_no
                    elif p_yes < 0.60:
                        side, price = "YES", p_yes

                    if not side:
                        continue

                    # Stake dinámico
                    pct = min(MAX_POSITION_PCT_BASE + edge * 200, MAX_POSITION_PCT_MAX)  # Escala con edge
                    stake = round(self.state["balance"] * pct, 2)
                    if stake < 1.0:
                        continue

                    self.state["balance"] -= stake
                    net_win = round((stake / price - stake) * (1 - COMISION), 2)

                    self.state["open_trades"][mid] = {
                        "city": city,
                        "question": question[:100],
                        "side": side,
                        "price": price,
                        "stake": stake,
                        "net_win": net_win,
                        "forecast_temp": forecast_temp,
                        "date": datetime.utcnow().isoformat()
                    }
                    msg = f"🎯 TRADE {city}: {side} @ {price:.3f} | Edge {edge*100:.2f}% | Stake ${stake} | Forecast {forecast_temp}°F"
                    logger.info(msg)
                    scanned += 1
                    break  # Uno por ciudad
            except Exception as e:
                logger.error(f"Error {city}: {e}")
        logger.info(f"Escaneados: {scanned} trades nuevos")

    def run_cycle(self):
        self.resolve_trades()
        self.scan_markets()
        win_rate = self.state["wins"] / self.state["total_trades"] * 100 if self.state["total_trades"] else 0
        roi = (self.state["balance"] - self.initial_balance) / self.initial_balance * 100
        hist = {
            "balance": self.state["balance"],
            "win_rate": win_rate,
            "roi": roi,
            "open_trades": len(self.state["open_trades"]),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.state["history"].append(hist)
        self._save_state()
        logger.info(f"✅ Ciclo OK | Balance: ${self.state['balance']:.2f} | ROI: {roi:.1f}% | Open: {len(self.state['open_trades'])}")

# ==========================
# MAIN - LOOP INFINITO O MÚLTIPLES CICLOS
# ==========================
if __name__ == "__main__":
    bot = PolyWeatherBot()
    try:
        cycles = 10 if BACKTEST_MODE else float('inf')  # Infinito en prod
        for i in range(cycles):
            logger.info(f"\n--- Ciclo {i+1} ---")
            bot.run_cycle()
            if i < cycles - 1:
                time.sleep(CYCLE_SLEEP)
    except KeyboardInterrupt:
        logger.info("🛑 Detenido por usuario")
        bot._save_state()
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        bot._save_state()
