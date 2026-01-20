import requests
import json
import os
import re
import math
import time
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ==========================
#        CONFIGURACIÓN
# ==========================
VERSION = "6.7.0-HIGH_VOLUME"
print(f"🚀 [INIT] WeatherTrader {VERSION} | {datetime.now().strftime('%H:%M:%S')}")

CAPITAL_INICIAL = 196.70
EDGE_THRESHOLD_BASE = 0.05      # ⚡ Bajado al 5% para capturar más oportunidades
MAX_EVENT_EXPOSURE = 0.03       # 3% máximo por cada ciudad
MAX_CLUSTER_EXPOSURE = 0.15     # ⚡ Aumentado al 15% para permitir más trades simultáneos
KELLY_FRACTION_BASE = 0.20      # Fracción de Kelly ajustada para el nuevo volumen
COMISION_GANANCIA = 0.02        

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

class WeatherTraderLive:
    def __init__(self):
        self.session = self._configurar_sesion()
        self.data = self._cargar_datos()
        self.pendientes = self._cargar_pendientes()
        
        # 🌍 Panel ampliado a 12 ciudades para mayor frecuencia de trading
        self.ciudades_config = {
            "Seoul": {"lat": 37.56, "lon": 126.97},
            "Atlanta": {"lat": 33.74, "lon": -84.38},
            "Dallas": {"lat": 32.77, "lon": -96.79},
            "Seattle": {"lat": 47.60, "lon": -122.33},
            "New York": {"lat": 40.71, "lon": -74.00},
            "London": {"lat": 51.50, "lon": -0.12},
            "Toronto": {"lat": 43.65, "lon": -79.38},
            "Buenos Aires": {"lat": -34.60, "lon": -58.38},
            "Chicago": {"lat": 41.87, "lon": -87.62},
            "Los Angeles": {"lat": 34.05, "lon": -118.24},
            "Tokyo": {"lat": 35.68, "lon": 139.76},
            "Sydney": {"lat": -33.86, "lon": 151.20}
        }
        
        if not os.path.exists("reports"):
            os.makedirs("reports")

    def _configurar_sesion(self):
        sesion = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], raise_on_status=False)
        sesion.mount('https://', HTTPAdapter(max_retries=retries))
        return sesion

    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json", 'r') as f:
                    d = json.load(f)
                    d.setdefault("balance", CAPITAL_INICIAL)
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

    def guardar_estado(self):
        with open("mercados_pendientes.json", "w") as f: json.dump(self.pendientes, f, indent=2)
        with open("billetera_virtual.json", "w") as f: json.dump(self.data, f, indent=2)

    def safe_price(self, p_raw):
        try: return float(p_raw) if p_raw and 0 < float(p_raw) < 1 else None
        except: return None

    def consultar_clima(self, url, params):
        try:
            res = self.session.get(url, params=params, timeout=20)
            res.raise_for_status()
            return res.json()
        except: return None

    def calibrar_sigma(self, lat, lon):
        end_d = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_d = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        res = self.consultar_clima("https://archive-api.open-meteo.com/v1/archive", 
                                   {"latitude": lat, "longitude": lon, "start_date": start_d, "end_date": end_d,
                                    "daily": "temperature_2m_max", "timezone": "auto"})
        hist = res.get('daily', {}).get('temperature_2m_max', []) if res else []
        if not hist or len(hist) < 10: return 1.3
        mean = sum(hist)/len(hist)
        variance = sum((t-mean)**2 for t in hist)/len(hist)
        return max(0.6, math.sqrt(variance))

    def resolver_mercados(self):
        hoy = datetime.now().strftime('%Y-%m-%d')
        pendientes_act = {}
        for m_id, m in self.pendientes.items():
            if m.get('fecha_expiracion') and m['fecha_expiracion'] < hoy:
                res = self.consultar_clima("https://archive-api.open-meteo.com/v1/archive", 
                                           {"latitude": m['lat'], "longitude": m['lon'], "start_date": m['fecha_expiracion'], "end_date": m['fecha_expiracion'],
                                            "daily": "temperature_2m_max", "timezone": "auto"})
                t_real = res.get('daily', {}).get('temperature_2m_max', [None])[0] if res else None
                if t_real is not None:
                    exito = (t_real > m['umbral']) if m['op'] == ">" else (t_real < m['umbral'])
                    gano = (m['lado'] == "YES" and exito) or (m['lado'] == "NO" and not exito)
                    profit = m['win_neto'] if gano else -m['stake']
                    self.data["balance"] += profit
                    print(f"💰 RESUELTO: {m['ciudad']} | Real: {t_real}°C | {'GANADO' if gano else 'PERDIDO'} | Net: ${profit:.2f}")
                else:
                    pendientes_act[m_id] = m
            else:
                pendientes_act[m_id] = m
        self.pendientes = pendientes_act

    def generar_reporte(self):
        try:
            hist = [h['balance'] for h in self.data['historial']]
            if len(hist) < 2: return
            equity = np.array(hist)
            peak = np.maximum.accumulate(equity)
            drawdown = equity - peak

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
            ax1.plot(equity, color='#2ecc71', lw=2)
            ax1.set_title(f"Equity Curve | Balance: ${self.data['balance']:.2f}")
            ax1.grid(True, alpha=0.3)
            ax2.fill_between(range(len(drawdown)), drawdown, 0, color='#e74c3c', alpha=0.3)
            ax2.set_ylabel("Drawdown ($)")
            ax2.grid(True, alpha=0.3)

            ts = datetime.now().strftime("%Y%m%d_%H%M")
            plt.tight_layout()
            plt.savefig(f"reports/status_{ts}.png")
            plt.close()
            
            files = sorted([os.path.join("reports", f) for f in os.listdir("reports") if f.endswith(".png")])
            if len(files) > 5: os.remove(files[0])
        except: pass

    def escanear_mercado(self, ciudad, config):
        if any(m.get("ciudad") == ciudad for m in self.pendientes.values()): return
        riesgo_actual = sum(m['stake'] for m in self.pendientes.values())
        if riesgo_actual >= self.data["balance"] * MAX_CLUSTER_EXPOSURE: return

        try:
            params = {"active":"true","closed":"false","query":ciudad,"limit":15}
            res_gamma = self.session.get(GAMMA_API_URL, params=params, timeout=20).json()
            if not isinstance(res_gamma, list): return

            res_f = self.consultar_clima("https://api.open-meteo.com/v1/forecast", 
                                         {"latitude": config['lat'], "longitude": config['lon'], 
                                          "daily":"temperature_2m_max", "timezone":"auto", "forecast_days":1})
            t_forecast = res_f.get('daily',{}).get('temperature_2m_max',[None])[0]
            if t_forecast is None: return

            sigma = self.calibrar_sigma(config['lat'], config['lon'])

            for mkt in res_gamma:
                if float(mkt.get("liquidity", 0)) < 1000: continue
                pregunta = mkt.get("question","").lower()
                match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", pregunta)
                if not match: continue
                threshold = float(match.group(1))
                if match.group(2) in ["f", "fahrenheit"]: threshold = (threshold - 32)*5/9
                op = "<" if any(w in pregunta for w in ["below","under","less"]) else ">"

                try:
                    outcomes = json.loads(mkt.get("outcomes","[]"))
                    prices = json.loads(mkt.get("outcomePrices","[]"))
                    mapping = dict(zip([o.lower() for o in outcomes], prices))
                    p_yes, p_no = self.safe_price(mapping.get("yes")), self.safe_price(mapping.get("no"))
                    if not p_yes or not p_no: continue
                except: continue

                z = (t_forecast - threshold)/sigma
                prob_gt = max(0.001, min(0.999, 0.5*(1 + math.erf(z/math.sqrt(2)))))
                prob_yes = prob_gt if op==">" else 1-prob_gt
                lado, prob, precio = ("YES", prob_yes, p_yes) if prob_yes>p_yes else ("NO", 1-prob_yes, p_no)
                edge = prob - precio

                if edge > EDGE_THRESHOLD_BASE:
                    b = (1/precio)-1
                    kelly = min((b*prob - (1-prob))/b, 0.5)*KELLY_FRACTION_BASE*(1.3/sigma)
                    if kelly > 0.01:
                        stake = (self.data["balance"]-riesgo_actual)*min(kelly, MAX_EVENT_EXPOSURE)
                        if stake < 1: continue
                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": round(prob,4), "precio": precio,
                            "stake": round(stake,2), "umbral": threshold, "op": op,
                            "win_neto": round((stake * b) * (1 - COMISION_GANANCIA), 2),
                            "fecha_expiracion": mkt.get("endDate","").split("T")[0],
                            "lat": config["lat"], "lon": config["lon"], "sigma": round(sigma,2)
                        }
                        riesgo_actual += stake
                        print(f"🎯 TRADE: {ciudad} | {lado} | Edge: {edge:.1%} | Stake: ${stake:.2f}")
        except Exception as e:
            print(f"⚠️ Error {ciudad}: {e}")

    def ejecutar_ciclo_unico(self):
        print("⚙️ Ejecutando análisis de mercado (Ciclo Único)...")
        self.resolver_mercados()
        for ciudad, config in self.ciudades_config.items():
            self.escanear_mercado(ciudad, config)
        
        self.data["historial"].append({
            "fecha": datetime.now().strftime("%d/%m %H:%M"),
            "balance": self.data["balance"]
        })
        if self.data["balance"] > self.data["peak_balance"]:
            self.data["peak_balance"] = self.data["balance"]
            
        self.generar_reporte()
        self.guardar_estado()
        print(f"✅ Ciclo finalizado exitosamente | Balance: ${self.data['balance']:.2f}")

if __name__ == "__main__":
    WeatherTraderLive().ejecutar_ciclo_unico()
