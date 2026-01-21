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
# CONFIGURACIÓN GENERAL - BOT METEO PRO CON FORECAST (OPENWEATHER + WTTR FALLBACK)
# ==========================
VERSION = "10.2-WTTR-FALLBACK-PRO-METEO-BOT"

CAPITAL_INICIAL = 40.00

EDGE_MIN = 0.0005
MAX_POSITION_PCT_BASE = 0.05
MAX_POSITION_PCT_MAX = 0.10
MAX_OPEN_TRADES = 15
COMISION = 0.001
MIN_LIQUIDITY = 50

GAMMA_API = "https://gamma-api.polymarket.com/markets"

# OpenWeatherMap (TU KEY YA ACTIVA!)
OPENWEATHER_API_KEY = "25ed3ded0753b35ae362ac1d888b0528"  # ¡TU KEY ACTIVE! Cambia si regeneras
OPENWEATHER_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"

# Email alerts (opcional)
EMAIL_SENDER = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_RECIPIENT = "your_email@gmail.com"
ENABLE_EMAIL_ALERTS = False

# Opciones
ENABLE_FORECAST = True  # Siempre ON (fallback wttr.in si OpenWeather falla)
ENABLE_DIVERSIFICATION = False
BACKTEST_MODE = False  # True=10 ciclos finitos
CYCLE_SLEEP = 60  # Segundos (60=test, 300=prod)

# Ciudades (mapping OpenWeather/wttr.in)
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

# Logging (consola + bot.log)
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', 
                    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()])
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
                    loaded = json.load(f)
                    if 'balance' not in loaded or not isinstance(loaded['balance'], (int, float)):
                        raise ValueError("Balance inválido")
                    return loaded
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
        """Forecast PRO: OpenWeather (tu key) → wttr.in fallback (siempre gratis)"""
        # TRY 1: OpenWeather (prioridad)
        if OPENWEATHER_API_KEY != "your_openweather_api_key_here":
            try:
                tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
                url = f"{OPENWEATHER_FORECAST}?q={city_ow}&appid={OPENWEATHER_API_KEY}&units=imperial&cnt=8"
                r = self.session.get(url, timeout=10).json()
                highs = [f['main']['temp_max'] for f in r.get('list', []) 
                         if 'dt_txt' in f and tomorrow in f['dt_txt']]
                if highs:
                    temp = max(highs)
                    logger.info(f"🌦️ OpenWeather OK {city_ow}: {temp:.1f}°F")
                    return temp
            except Exception as e:
                logger.warning(f"OpenWeather fail ({e}) → wttr.in fallback")

        # TRY 2: wttr.in (ILIMITADO GRATIS, no key)
        try:
            city_simple = city_ow.split(',')[0].replace(' ', '+')  # "New+York"
            url = f"https://wttr.in/{city_simple}?format=j1"
            r = self.session.get(url, timeout=10).json()
            if 'forecast' in r and len(r['forecast']) > 1:
                tomorrow_data = r['forecast'][1]
                maxt = tomorrow_data.get('maxtempF') or tomorrow_data.get('tempF')
                if maxt:
                    temp = float(maxt)
                    logger.info(f"🌦️ wttr.in OK {city_ow}: {temp:.1f}°F")
                    return temp
        except Exception as e:
            logger.warning(f"wttr.in fail ({e}) → No forecast")

        logger.warning(f"No forecast para {city_ow}")
        return None

    def parse_temp_expectation(self, question):
        """Parsea temp expectativa del mercado"""
        q = question.lower()
        unit = 'f' if any(x in q for x in ['°f', 'fahrenheit']) else 'c' if any(x in q for x in ['°c', 'celsius']) else 'f'
        nums = re.findall(r'(\d+(?:\.\d+)?)', q)
        if not nums:
            return None
        exp_low = float(nums[0])
        exp_high = exp_low
        if len(nums) > 1:
            exp_high = float(nums[1])
        is_narrow = exp_high - exp_low < 5 or any(k in q for k in ['exact', 'between'])
        is_above = any(k in q for k in ['above', 'exceed'])
        is_below = 'below' in q
        return {
            "low": exp_low,
            "high": exp_high,
            "unit": unit,
            "is_narrow": is_narrow,
            "is_above": is_above,
            "is_below": is_below
        }

    def has_forecast_edge(self, question, forecast_temp):
        """¿Forecast favorece NO?"""
        if not forecast_temp:
            return False
        temp_exp = self.parse_temp_expectation(question)
        if not temp_exp:
            return False
        exp_low, exp_high = temp_exp['low'], temp_exp['high']
        if temp_exp['is_narrow'] and not (exp_low <= forecast_temp <= exp_high):
            return True
        if temp_exp['is_above'] and forecast_temp < exp_low:
            return True
        if temp_exp['is_below'] and forecast_temp > exp_high:
            return True
        return False

    def is_weather_market(self, question):
        q = question.lower()
        keywords = ["temperature", "temp", "degree", "°", "high", "max", "above", "below", "reach", "exceed", "between", "exact"]
        return any(k in q for k in keywords)

    def resolve_trades(self):
        if not self.state["open_trades"]:
            return
        active = {}
        resolved = []
        for mid, trade in list(self.state["open_trades"].items()):
            try:
                r = self.session.get(f"{GAMMA_API}/{mid}", timeout=10).json()
                if r.get("closed") is True:
                    winner_idx = r.get("winnerOutcomeIndex")
                    winner_side = "YES" if str(winner_idx) == "0" else "NO"
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
                    # Elimina resolved
                    if mid in self.state["open_trades"]:
                        del self.state["open_trades"][mid]
                else:
                    active[mid] = trade
            except Exception as e:
                logger.warning(f"Error resolve {mid}: {e}")
                active[mid] = trade
        self.state["open_trades"].update(active)  # Actualiza con restantes
        if resolved:
            win_rate = self.state["wins"] / self.state["total_trades"] * 100 if self.state["total_trades"] else 0
            roi = (self.state["balance"] - self.initial_balance) / self.initial_balance * 100 if self.initial_balance else 0
            summary = f"Resueltos: {len(resolved)} | Win Rate: {win_rate:.1f}% | ROI: {roi:.1f}% | Balance: ${self.state['balance']:.2f}"
            logger.info(summary)
            self._send_email_alert("PolyWeatherBot: Trades Resueltos", "\n".join(resolved) + "\n" + summary)

    def scan_markets(self):
        logger.info("🌦️ Escaneando mercados...")
        scanned = 0
        for city, city_ow in CITIES.items():
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                logger.warning("Límite trades abiertos alcanzado")
                break
            forecast_temp = self._get_weather_forecast(city_ow)
            try:
                params = {"active": "true", "query": city, "limit": "30"}
                markets = self.session.get(GAMMA_API, params=params, timeout=15).json()
                for m in markets:
                    mid = m.get("id")
                    if not mid or mid in self.state["open_trades"]:
                        continue
                    question = m.get("question", "")
                    if not ENABLE_DIVERSIFICATION and not self.is_weather_market(question):
                        continue
                    liquidity = float(m.get("liquidity", 0))
                    if liquidity < MIN_LIQUIDITY:
                        continue
                    outcome_prices_str = m.get("outcomePrices", "[]")
                    prices = json.loads(outcome_prices_str)
                    if len(prices) != 2:
                        continue
                    p_yes = float(prices[0])
                    p_no = float(prices[1])
                    if not (0.01 < p_yes < 0.99 and 0.01 < p_no < 0.99):
                        continue
                    edge = abs(1 - (p_yes + p_no))
                    if edge < EDGE_MIN:
                        continue

                    # Decisión con forecast bias fuerte a NO
                    forecast_good_for_no = self.has_forecast_edge(question, forecast_temp)
                    side, price = None, None
                    if (forecast_good_for_no or p_no < p_yes) and p_no < 0.60:
                        side, price = "NO", p_no
                    elif p_yes < 0.60:
                        side, price = "YES", p_yes

                    if not side:
                        continue

                    # Stake dinámico
                    pct = min(MAX_POSITION_PCT_BASE + (edge * 200), MAX_POSITION_PCT_MAX)
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
                logger.error(f"Error scan {city}: {e}")
        logger.info(f"Escaneo completo: {scanned} trades nuevos | Abiertos: {len(self.state['open_trades'])}")

    def run_cycle(self):
        self.resolve_trades()
        self.scan_markets()
        win_rate = self.state["wins"] / self.state["total_trades"] * 100 if self.state["total_trades"] else 0
        roi = (self.state["balance"] - self.initial_balance) / self.initial_balance * 100 if self.initial_balance else 0
        hist = {
            "balance": round(self.state["balance"], 2),
            "win_rate": round(win_rate, 2),
            "roi": round(roi, 2),
            "open_trades": len(self.state["open_trades"]),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.state["history"].append(hist)
        self._save_state()
        logger.info(f"✅ Ciclo OK | Balance: ${self.state['balance']:.2f} | Win Rate: {win_rate:.1f}% | ROI: {roi:.1f}% | Open: {len(self.state['open_trades'])}")

# ==========================
# MAIN - LOOP INFINITO/BACKTEST
# ==========================
if __name__ == "__main__":
    bot = PolyWeatherBot()
    try:
        infinite = not BACKTEST_MODE
        counter = 0
        num_cycles = 10 if BACKTEST_MODE else float('inf')
        while infinite or counter < num_cycles:
            logger.info(f"\n--- Ciclo {counter+1} ---")
            bot.run_cycle()
            counter += 1
            if not infinite and counter >= num_cycles:
                break
            time.sleep(CYCLE_SLEEP)
        logger.info("🎉 Backtest/Pruebas completadas")
    except KeyboardInterrupt:
        logger.info("🛑 Detenido por usuario (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
    finally:
        bot._save_state()
        logger.info("💾 State guardado. ¡Hasta la próxima!")
