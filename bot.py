import requests
import json
import os
import sys
import time
import re
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from scipy.stats import norm

# ==========================
# CONFIGURACIÓN (Variables de Entorno)
# ==========================
VERSION = "10.1-RENDER-PROD"
CAPITAL_INICIAL = float(os.getenv('CAPITAL_INICIAL', 100.00))
EDGE_THRESHOLD = float(os.getenv('EDGE_THRESHOLD', 0.10))  # 10% de ventaja mínima
MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_PCT', 0.05)) # 5% por trade
MAX_OPEN_TRADES = int(os.getenv('MAX_OPEN_TRADES', 15))
COMISION = 0.00  # Polymarket no cobra fees de trading en CLOB (solo gas si ejecutas real)
MIN_LIQUIDITY_USD = 500  # Filtro suave para simulación

# APIs
GAMMA_API = "https://gamma-api.polymarket.com/markets"
CLOB_API = "https://clob.polymarket.com"

# Geolocalización para Forecasts
CITY_COORDS = {
    "New York": (40.7128, -74.0060, "fahrenheit"),
    "London": (51.5074, -0.1278, "celsius"),
    "Chicago": (41.8781, -87.6298, "fahrenheit"),
    "Los Angeles": (34.0522, -118.2437, "fahrenheit"),
    "San Francisco": (37.7749, -122.4194, "fahrenheit"),
    "Miami": (25.7617, -80.1918, "fahrenheit"),
    "Tokyo": (35.6762, 139.6503, "celsius"),
    "Seoul": (37.5665, 126.9780, "celsius")
}

class PolyWeatherBot:
    def __init__(self):
        self.session = self._create_session()
        self.state = self._load_state()
        print(f"🚀 {VERSION} INICIADO | Balance Simulado: ${self.state['balance']:.2f}")
        sys.stdout.flush()

    def _create_session(self):
        s = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _load_state(self):
        # En Render, el disco es efímero. Si reinicias, pierdes el state.json.
        # Para producción real necesitarías una BD (Redis/Postgres).
        # Aquí usamos un archivo local sabiendo esa limitación.
        if os.path.exists("state.json"):
            try:
                with open("state.json", "r") as f:
                    return json.load(f)
            except:
                pass
        return {"balance": CAPITAL_INICIAL, "open_trades": {}, "history": []}

    def _save_state(self):
        try:
            with open("state.json", "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error guardando estado: {e}")

    # --- LÓGICA DE FECHAS ---
    def get_market_date(self, question):
        """Intenta extraer la fecha objetivo del texto de la pregunta."""
        # Regex para formatos tipo "Jan 22", "January 22"
        match = re.search(r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d+)", question, re.IGNORECASE)
        
        if match:
            month_str = match.group(1)
            day_str = match.group(2)
            try:
                # Normalizar mes
                month_map = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month_num = month_map[month_str[:3].lower()]
                
                # Asumir año actual
                now = datetime.now()
                year = now.year
                
                # Crear fecha
                dt = datetime(year, month_num, int(day_str))
                
                # Si la fecha ya pasó hace mucho (ej. estamos en Ene y pregunta es Dic),
                # podría ser del año pasado, o si estamos en Dic y pregunta es Ene, año siguiente.
                # Simplificación: Si la fecha es ayer o antes, descartar.
                if dt.date() < (now.date() - timedelta(days=1)):
                    # Podría ser año siguiente
                    dt = dt.replace(year=year + 1)
                
                return dt
            except:
                return None
        return None

    # --- LÓGICA DE FORECAST ---
    def get_forecast_temp(self, city, target_date):
        """Obtiene la temperatura máxima pronosticada para una fecha específica."""
        if city not in CITY_COORDS:
            return None
            
        lat, lon, unit = CITY_COORDS[city]
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Open-Meteo da 7 días por defecto (indices 0 a 6)
        # target_date debe estar en ese rango
        if not target_date:
            return None
            
        delta_days = (target_date - today).days
        
        if delta_days < 0 or delta_days > 6:
            # Fuera del rango de forecast confiable
            return None

        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unit}&timezone=America/New_York"
        
        try:
            r = self.session.get(url, timeout=5).json()
            if "daily" in r and "temperature_2m_max" in r["daily"]:
                return r["daily"]["temperature_2m_max"][delta_days]
        except Exception as e:
            print(f"⚠️ Error Open-Meteo ({city}): {e}")
        return None

    # --- LÓGICA DE PRECIOS ---
    def get_clob_prices(self, market):
        """Obtiene el midpoint real del Order Book."""
        clob_ids = market.get("clobTokenIds", [])
        # A veces viene como string en JSON, a veces lista
        if isinstance(clob_ids, str):
            clob_ids = json.loads(clob_ids)
            
        if not clob_ids or len(clob_ids) != 2:
            return None, None

        yes_token = clob_ids[0]
        no_token = clob_ids[1]

        def get_mid(tid):
            try:
                r = self.session.get(f"{CLOB_API}/midpoint?token_id={tid}", timeout=2)
                if r.status_code == 200:
                    data = r.json()
                    return float(data.get("midpoint")) if "midpoint" in data else None
            except:
                pass
            return None

        p_yes = get_mid(yes_token)
        p_no = get_mid(no_token)
        return p_yes, p_no

    # --- MOTORES DE DECISIÓN ---
    def calculate_prob(self, forecast, lower, upper):
        if forecast is None: return None
        # Modelo Estadístico: Asumimos dist normal con Standard Deviation (Error) de 3.5 grados
        std_dev = 3.5 
        
        p_below_upper = norm.cdf(upper, loc=forecast, scale=std_dev) if upper != float('inf') else 1.0
        p_below_lower = norm.cdf(lower, loc=forecast, scale=std_dev) if lower != float('-inf') else 0.0
        
        return p_below_upper - p_below_lower

    def scan_markets(self):
        print("\n🔎 Escaneando mercados...")
        sys.stdout.flush()
        
        for city in CITY_COORDS.keys():
            if len(self.state["open_trades"]) >= MAX_OPEN_TRADES:
                print("🔒 Max trades alcanzado.")
                break

            # Búsqueda en Gamma
            params = {
                "limit": 20,
                "active": "true",
                "closed": "false",
                "search": f"highest temperature {city}"
            }
            try:
                markets = self.session.get(GAMMA_API, params=params).json()
            except:
                continue

            for m in markets:
                mid = m.get("id")
                if mid in self.state["open_trades"]: continue # Ya estamos dentro
                
                question = m.get("question", "")
                
                # 1. Parsear Fecha
                target_date = self.get_market_date(question)
                if not target_date: continue # No entendimos la fecha

                # 2. Obtener Forecast para ESA fecha
                forecast = self.get_forecast_temp(city, target_date)
                if forecast is None: continue

                # 3. Parsear Rango de Temperatura
                # Regex para "34-36°F", "above 40°F", etc.
                lower = float('-inf')
                upper = float('inf')
                
                range_match = re.search(r"(\d+)-(\d+)", question)
                above_match = re.search(r"(above|>)\s?(\d+)", question, re.IGNORECASE)
                below_match = re.search(r"(below|<)\s?(\d+)", question, re.IGNORECASE)
                
                if range_match:
                    lower = float(range_match.group(1))
                    upper = float(range_match.group(2))
                elif above_match:
                    lower = float(above_match.group(2))
                elif below_match:
                    upper = float(below_match.group(2))
                else:
                    continue # No entendimos el rango

                # 4. Calcular "My Prob"
                my_prob_yes = self.calculate_prob(forecast, lower, upper)
                if my_prob_yes is None: continue

                # 5. Obtener Precios Reales (CLOB)
                p_yes, p_no = self.get_clob_prices(m)
                if p_yes is None or p_no is None: continue
                
                # Filtro de Spread / Coherencia
                if (p_yes + p_no) < 0.90 or (p_yes + p_no) > 1.10: continue

                # 6. Calcular EDGE (Valor Esperado)
                # EV_YES = (Prob_Win * $1) - Cost
                ev_yes = my_prob_yes - p_yes
                
                # EV_NO = (Prob_Win_No * $1) - Cost_No
                # Prob_Win_No = 1 - my_prob_yes
                ev_no = (1.0 - my_prob_yes) - p_no

                best_side = None
                entry_price = 0
                edge = 0

                if ev_yes > EDGE_THRESHOLD:
                    best_side = "YES"
                    entry_price = p_yes
                    edge = ev_yes
                elif ev_no > EDGE_THRESHOLD:
                    best_side = "NO"
                    entry_price = p_no
                    edge = ev_no

                if best_side:
                    self.execute_trade(mid, city, question, best_side, entry_price, edge, forecast, target_date)

    def execute_trade(self, mid, city, question, side, price, edge, forecast, date_obj):
        stake = round(self.state["balance"] * MAX_POSITION_PCT, 2)
        if stake < 1.0: return # Mínimo $1

        self.state["balance"] -= stake
        self.state["open_trades"][mid] = {
            "city": city,
            "question": question,
            "side": side,
            "entry_price": price,
            "stake": stake,
            "forecast_at_entry": forecast,
            "edge": edge,
            "target_date_str": date_obj.strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat()
        }
        self._save_state()
        print(f"⚡ TRADE | {city} | {side} @ {price:.2f} | Edge {edge:.2f} | Fcst {forecast} | Fecha: {date_obj.strftime('%m-%d')}")
        sys.stdout.flush()

    def resolve_trades(self):
        # Revisa si los mercados abiertos han cerrado
        to_delete = []
        
        # Copia de keys para iterar seguro
        for mid in list(self.state["open_trades"].keys()):
            trade = self.state["open_trades"][mid]
            
            try:
                r = self.session.get(f"{GAMMA_API}/{mid}", timeout=5).json()
                
                if r.get("closed") is True:
                    # El mercado cerró
                    prices = json.loads(r.get("outcomePrices", "['0', '0']"))
                    
                    # Determinar ganador (Precios finales suelen ser 0 o 1)
                    final_yes = float(prices[0])
                    final_no = float(prices[1])
                    
                    won = False
                    if trade["side"] == "YES" and final_yes > 0.95: won = True
                    if trade["side"] == "NO" and final_no > 0.95: won = True
                    
                    pnl = 0
                    if won:
                        revenue = trade["stake"] / trade["entry_price"]
                        pnl = revenue - trade["stake"]
                        self.state["balance"] += revenue
                        print(f"✅ WIN | {trade['question'][:40]}... | +${pnl:.2f}")
                    else:
                        pnl = -trade["stake"]
                        print(f"❌ LOSS | {trade['question'][:40]}... | -${trade['stake']:.2f}")
                    
                    to_delete.append(mid)
            except Exception as e:
                print(f"Err checking {mid}: {e}")
        
        for mid in to_delete:
            del self.state["open_trades"][mid]
        
        if to_delete:
            self._save_state()

    def run(self):
        self.resolve_trades()
        self.scan_markets()

# ==========================
# LOOP INFINITO
# ==========================
if __name__ == "__main__":
    bot = PolyWeatherBot()
    
    while True:
        try:
            bot.run()
            print("💤 Durmiendo 15 minutos...")
            sys.stdout.flush()
            time.sleep(900) # 15 min pausa
        except KeyboardInterrupt:
            print("Apagando...")
            break
        except Exception as e:
            print(f"🔥 CRASH LOOP: {e}")
            time.sleep(60)
