import requests
import json
import os
import re
import math
import csv
from datetime import datetime, timedelta

# === METADATOS DE IDENTIDAD ===
VERSION = "6.4.0-QUANT_ADAPTIVE"
print(f"🚀 [INIT] WeatherTrader {VERSION} | {datetime.now().strftime('%H:%M:%S')}")

# === CONFIGURACIÓN INSTITUCIONAL ===
CAPITAL_INICIAL = 196.70  
EDGE_THRESHOLD_BASE = 0.07     
MAX_EVENT_EXPOSURE = 0.03 
MAX_CLUSTER_EXPOSURE = 0.08 
KELLY_FRACTION_BASE = 0.25     
COMISION_GANANCIA = 0.02  

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

class WeatherTraderV6_4_0:
    def __init__(self):
        self.data = self._cargar_datos()
        self.pendientes = self._cargar_pendientes()
        self.ciudades_config = {
            "Seoul": {"lat": 37.56, "lon": 126.97},
            "Atlanta": {"lat": 33.74, "lon": -84.38},
            "Dallas": {"lat": 32.77, "lon": -96.79},
            "Seattle": {"lat": 47.60, "lon": -122.33},
            "New York": {"lat": 40.71, "lon": -74.00},
            "London": {"lat": 51.50, "lon": -0.12}
        }

    # === PERSISTENCIA DE DATOS ===
    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json", 'r') as f:
                    d = json.load(f)
                    d.setdefault("peak_balance", d.get("balance", CAPITAL_INICIAL))
                    d.setdefault("historial", [])
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def _cargar_pendientes(self):
        if os.path.exists("mercados_pendientes.json"):
            try:
                with open("mercados_pendientes.json", 'r') as f: return json.load(f)
            except: pass
        return {}

    def safe_price(self, p_raw):
        try: return float(p_raw) if p_raw and 0 < float(p_raw) < 1 else None
        except: return None

    # === MOTOR DE CLIMA Y CALIBRACIÓN ===
    def consultar_clima(self, lat, lon, start_date, end_date):
        try:
            url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&daily=temperature_2m_max&timezone=auto"
            res = requests.get(url, timeout=15).json()
            return res.get('daily', {}).get('temperature_2m_max', [])
        except: return []

    def calibrar_sigma(self, lat, lon):
        # Calibración dinámica basada en los últimos 30 días
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        historial = self.consultar_clima(lat, lon, start_date, end_date)
        if not historial or len(historial) < 10: return 1.3
        
        mean = sum(historial) / len(historial)
        variance = sum((t - mean)**2 for t in historial) / len(historial)
        return max(0.6, math.sqrt(variance))

    # === RESOLUCIÓN DE MERCADOS (SETTLEMENT) ===
    def resolver_mercados_pendientes(self):
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        pendientes_actualizados = {}
        for m_id, m in self.pendientes.items():
            f_exp = m.get('fecha_expiracion')
            if f_exp and f_exp < hoy_str:
                # Consulta determinista de la fecha exacta
                temps = self.consultar_clima(m['lat'], m['lon'], f_exp, f_exp)
                t_real = temps[0] if temps else None
                if t_real is not None:
                    exito = (t_real > m['umbral']) if m['op'] == ">" else (t_real < m['umbral'])
                    gano = (m['lado'] == "YES" and exito) or (m['lado'] == "NO" and not exito)
                    res_dinero = m['win_neto'] if gano else -m['stake']
                    self.data["balance"] += res_dinero
                    self._registrar_auditoria(m, t_real, gano, res_dinero)
                    print(f"✅ RESOLVED: {m['ciudad']} | {f_exp} | T_Real: {t_real}°C | {'WIN' if gano else 'LOSS'}")
                else:
                    pendientes_actualizados[m_id] = m
            else:
                pendientes_actualizados[m_id] = m
        self.pendientes = pendientes_actualizados

    def _registrar_auditoria(self, m, t_real, gano, res):
        file_exists = os.path.isfile("auditoria_detallada.csv")
        with open("auditoria_detallada.csv", 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp","Ciudad","Lado","Prob","Precio","Stake","Umbral","Op","T_Real","Resultado_USD","Kelly_f","Sigma"])
            writer.writerow([datetime.now(), m['ciudad'], m['lado'], f"{m['prob']:.4f}", f"{m['precio']:.4f}", f"{m['stake']:.2f}", m['umbral'], m['op'], t_real, f"{res:.2f}", f"{m.get('kelly_teorico',0):.4f}", m.get('sigma_usada',1.3)])

    # === EJECUCIÓN DE TRADES ADAPTATIVOS ===
    def ejecutar_trade(self, ciudad, config):
        if any(m.get("ciudad") == ciudad for m in self.pendientes.values()): return
        riesgo_total = sum(m.get('stake', 0) for m in self.pendientes.values())
        if riesgo_total >= (self.data["balance"] * MAX_CLUSTER_EXPOSURE): return

        try:
            params = {"active": "true", "closed": "false", "query": ciudad, "limit": 25}
            markets_raw = requests.get(GAMMA_API_URL, params=params, timeout=15).json()
            if not isinstance(markets_raw, list): return

            url_f = f"https://api.open-meteo.com/v1/forecast?latitude={config['lat']}&longitude={config['lon']}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            t_forecast = requests.get(url_f, timeout=10).json().get('daily', {}).get('temperature_2m_max', [None])[0]
            if t_forecast is None: return

            sigma = self.calibrar_sigma(config['lat'], config['lon'])

            # Lógica Adaptativa: Penaliza volatilidad alta
            edge_threshold = EDGE_THRESHOLD_BASE * (1 + 0.5 * (sigma - 1.3))
            kelly_fraction = KELLY_FRACTION_BASE * (1.3 / sigma)

            for mkt in markets_raw:
                pregunta = mkt.get("question", "").lower()
                if not any(k in pregunta for k in ["temperature", "degrees", "°", "high"]): continue
                if float(mkt.get("liquidity", 0)) < 1000: continue

                match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", pregunta)
                if not match: continue

                threshold = float(match.group(1))
                if match.group(2) in ["f", "fahrenheit"]: threshold = (threshold - 32) * 5/9
                op = "<" if any(w in pregunta for w in ["below", "under", "less"]) else ">"

                try:
                    outcomes = json.loads(mkt.get("outcomes", "[]"))
                    prices = json.loads(mkt.get("outcomePrices", "[]"))
                    mapping = dict(zip([o.lower() for o in outcomes], prices))
                    p_yes, p_no = self.safe_price(mapping.get("yes")), self.safe_price(mapping.get("no"))
                    if p_yes is None or p_no is None: continue
                except: continue

                # Probabilidad Gaussiana
                z = (t_forecast - threshold) / sigma
                prob_gt = max(0.001, min(0.999, 0.5 * (1 + math.erf(z / math.sqrt(2)))))
                prob_yes = prob_gt if op == ">" else 1 - prob_gt

                lado, prob, precio = ("YES", prob_yes, p_yes) if prob_yes > p_yes else ("NO", 1 - prob_yes, p_no)
                edge = prob - precio

                if edge > edge_threshold:
                    b = (1 / precio) - 1
                    kelly_f = min((b * prob - (1 - prob)) / b, 0.5)
                    kelly_f *= kelly_fraction
                    
                    if kelly_f > 0.01:
                        stake_pct = min(kelly_f, MAX_EVENT_EXPOSURE)
                        stake = (self.data["balance"] - riesgo_total) * stake_pct
                        if stake < 1.0: continue
                        
                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": round(prob, 4), "precio": precio,
                            "stake": round(stake, 2), "umbral": threshold, "op": op,
                            "win_neto": round((stake * b) * (1 - COMISION_GANANCIA), 2),
                            "fecha_expiracion": mkt.get("endDate", "").split("T")[0],
                            "lat": config["lat"], "lon": config["lon"],
                            "kelly_teorico": round(kelly_f, 4), "sigma_usada": round(sigma, 2)
                        }
                        riesgo_total += stake
                        print(f"🎯 TRADE: {ciudad} | {lado} | Edge: {edge:.2%} | Sigma: {sigma:.2f}")

        except Exception as e: print(f"⚠️ Error {ciudad}: {e}")

    # === CICLO PRINCIPAL ===
    def ejecutar(self):
        self.resolver_mercados_pendientes()
        for ciudad, config in self.ciudades_config.items():
            self.ejecutar_trade(ciudad, config)

        self.data["historial"].append({"fecha": datetime.now().strftime("%d/%m %H:%M"), "balance": self.data["balance"]})
        with open("mercados_pendientes.json", "w") as f: json.dump(self.pendientes, f, indent=2)
        with open("billetera_virtual.json", "w") as f: json.dump(self.data, f, indent=2)
        print(f"📈 [FINAL] Equity: ${self.data['balance']:.2f} | Activos: {len(self.pendientes)}")

if __name__ == "__main__":
    WeatherTraderV6_4_0().ejecutar()
