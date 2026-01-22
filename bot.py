import requests
import json
import os
import sys
import time
import re
from datetime import datetime, timedelta, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from scipy.stats import norm

# ==========================
# CONFIGURACIÓN
# ==========================
VERSION = "10.2-DEBUG-MODE"
CAPITAL_INICIAL = float(os.getenv('CAPITAL_INICIAL', 100.00))
EDGE_THRESHOLD = float(os.getenv('EDGE_THRESHOLD', 0.10))
MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_PCT', 0.05))
MAX_OPEN_TRADES = int(os.getenv('MAX_OPEN_TRADES', 15))
MIN_LIQUIDITY_USD = 500
VERBOSE = True # ¡ACTIVADO PARA VER TODO EN LOS LOGS!

# APIs
GAMMA_API = "https://gamma-api.polymarket.com/markets"
CLOB_API = "https://clob.polymarket.com"

CITY_COORDS = {
    "New York": (40.7128, -74.0060, "fahrenheit"),
    "London": (51.5074, -0.1278, "celsius"),
    "Chicago": (41.8781, -87.6298, "fahrenheit"),
    "Los Angeles": (34.0522, -118.2437, "fahrenheit"),
    "Miami": (25.7617, -80.1918, "fahrenheit"),
}

class PolyWeatherBot:
    def __init__(self):
        self.session = self._create_session()
        self.state = self._load_state()
        print(f"🚀 {VERSION} | Balance: ${self.state['balance']:.2f}")
        sys.stdout.flush()

    def _create_session(self):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _load_state(self):
        if os.path.exists("state.json"):
            try:
                with open("state.json", "r") as f:
                    return json.load(f)
            except: pass
        return {"balance": CAPITAL_INICIAL, "open_trades": {}}

    def _save_state(self):
        try:
            with open("state.json", "w") as f:
                json.dump(self.state, f, indent=2)
        except: pass

    # --- PARSING FECHAS (FIXED) ---
    def get_market_date(self, question):
        # Busca "Jan 22", "Feb 10", etc.
        match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d+)", question, re.IGNORECASE)
        if match:
            try:
                month_map = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
                month = month_map[match.group(1)[:3].lower()]
                day = int(match.group(2))
                now = datetime.now()
                # Asumimos año actual
                dt = datetime(now.year, month, day)
                # Si la fecha es ayer o antes, asumimos año siguiente
                if dt.date() < (now.date() - timedelta(days=1)):
                    dt = dt.replace(year=now.year + 1)
                return dt
            except: return None
        return None

    # --- PRECIOS CLOB ---
    def get_clob_prices(self, market):
        clob_ids = market.get("clobTokenIds", [])
        if isinstance(clob_ids, str): clob_ids = json.loads(clob_ids)
        if not clob_ids or len(clob_ids) != 2: return None, None

        def get_mid(tid):
            try:
                r = self.session.get(f"{CLOB_API}/midpoint?token_id={tid}", timeout=2)
                if r.status_code == 200:
                    return float(r.json().get("midpoint"))
            except: return None
            return None

        return get_mid(clob_ids[0]), get_mid(clob_ids[1])

    # --- FORECAST ---
    def get_forecast(self, city, target_date):
        lat, lon, unit = CITY_COORDS.get(city, (0,0,"celsius"))
        today = datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        if not target_date: return None
        
        delta = (target_date - today).days
        if delta < 0 or delta > 6: return None # Solo forecast a 7 dias

        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unit}&timezone=America/New_York"
        try:
            r = self.session.get(url, timeout=4).json()
            return r["daily"]["temperature_2m_max"][delta]
        except: return None

    # --- LÓGICA PRINCIPAL ---
    def scan_markets(self):
        print(f"\n🔎 Escaneando mercados... (Hora: {datetime.now().strftime('%H:%M:%S')})")
        sys.stdout.flush()

        for city in CITY_COORDS.keys():
            # Busqueda más amplia para encontrar algo
            params = {"limit": 15, "active": "true", "closed": "false", "search": city}
            try:
                markets = self.session.get(GAMMA_API, params=params).json()
            except Exception as e:
                print(f"⚠️ Error API Gamma: {e}")
                continue

            if VERBOSE: print(f"  > Ciudad: {city} | Mercados encontrados: {len(markets)}")

            for m in markets:
                q = m.get("question", "")
                
                # Filtro 1: Texto Relevante
                if "temperature" not in q.lower() and "high" not in q.lower():
                    continue

                # Filtro 2: Fecha
                target_date = self.get_market_date(q)
                if not target_date:
                    if VERBOSE: print(f"    [SKIP] No entendí fecha: {q[:30]}...")
                    continue
                
                # Filtro 3: Forecast
                forecast = self.get_forecast(city, target_date)
                if forecast is None:
                    if VERBOSE: print(f"    [SKIP] Sin forecast para {target_date.date()}")
                    continue

                # Filtro 4: Precios CLOB
                p_yes, p_no = self.get_clob_prices(m)
                if p_yes is None or p_no is None:
                    if VERBOSE: print(f"    [SKIP] Sin liquidez en CLOB")
                    continue

                # Logica Probabilidad (Simplificada para debug)
                # Buscamos numeros en la pregunta
                nums = re.findall(r"\d+", q)
                if not nums: continue
                strike = float(nums[0]) # Tomamos el primer numero como strike aprox

                # Calculo rapido de dirección
                my_view = "YES" if forecast > strike + 2 else "NO"
                if "below" in q.lower() or "<" in q:
                    my_view = "YES" if forecast < strike - 2 else "NO"

                # Debug print del analisis
                print(f"    👀 {q[:40]}... | Fcst: {forecast} | Strike: {strike} | Precio YES: {p_yes:.2f}")

                # Aquí iría la ejecución (omitida en Debug para no gastar logs, solo ver lógica)
                # Si quieres que ejecute, descomenta la lógica de trade de la v10.1

    def run(self):
        self.scan_markets()

if __name__ == "__main__":
    bot = PolyWeatherBot()
    while True:
        bot.run()
        print("💤 Durmiendo 10 minutos...")
        sys.stdout.flush()
        time.sleep(600)
