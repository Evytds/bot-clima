import requests
import json
import os
import re
import math
import pandas as pd
from datetime import datetime, timedelta

# === CONFIGURACIÓN QUANT v4.4 ===
CAPITAL_INICIAL = 196.70
BASE_SIGMA = 1.3          # Error estándar del pronóstico en °C
EDGE_THRESHOLD = 0.07     # Ventaja mínima requerida (7%)
MAX_EVENT_EXPOSURE = 0.02 # Máximo 2% de capital por operación individual
MAX_CLUSTER_EXPOSURE = 0.05 # Máximo 5% de riesgo total acumulado (Cluster Cap)
COMISION_GANANCIA = 0.02  # Fee de Polymarket sobre beneficios netos

ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_PENDIENTES = "mercados_pendientes.json"
ARCHIVO_DASHBOARD = "index.html"

class WeatherTraderV4_4:
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
        self.poly_url = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    d = json.load(f)
                    d.setdefault("peak_balance", d["balance"])
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def _cargar_pendientes(self):
        if os.path.exists(ARCHIVO_PENDIENTES):
            try:
                with open(ARCHIVO_PENDIENTES, 'r') as f: return json.load(f)
            except: pass
        return {}

    def obtener_capital_en_riesgo(self):
        return sum(m['stake'] for m in self.pendientes.values())

    def parsear_mercado_robusto(self, pregunta):
        # Captura número y unidad (Celsius o Fahrenheit)
        match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", pregunta, re.IGNORECASE)
        if match:
            threshold = float(match.group(1))
            unidad = match.group(2).lower()
        else:
            nums = re.findall(r"[-+]?\d*\.?\d+", pregunta)
            if not nums: return None, None
            threshold = float(nums[0])
            unidad = "c"
        
        # Conversión Fahrenheit a Celsius si es necesario
        if unidad in ["f", "fahrenheit"]:
            threshold = (threshold - 32) * 5/9
            
        op = "<" if any(w in pregunta.lower() for w in ["below", "under", "less", "lower"]) else ">"
        return threshold, op

    def resolver_mercados_pendientes(self):
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        pendientes_actualizados = {}
        
        for m_id, m in self.pendientes.items():
            if m['fecha_expiracion'] < hoy_str:
                t_real = self.obtener_clima_historico(m['lat'], m['lon'], m['fecha_expiracion'])
                if t_real is not None:
                    exito = (t_real > m['umbral']) if m['op'] == ">" else (t_real < m['umbral'])
                    gano = (m['lado'] == "YES" and exito) or (m['lado'] == "NO" and not exito)
                    
                    outcome_real = 1 if gano else 0
                    res_dinero = m['win_neto'] if gano else -m['stake']
                    brier_comp = (m['prob'] - outcome_real) ** 2

                    self.data["balance"] += res_dinero
                    
                    with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
                        f.write(f"{datetime.now()},{m['ciudad']},{m['lado']},{m['prob']:.4f},{m['precio']:.2f},{m['stake']:.2f},{m['ev']:.2f},{res_dinero:.2f},{brier_comp:.4f},{t_real:.2f}\n")
                else:
                    pendientes_actualizados[m_id] = m
            else:
                pendientes_actualizados[m_id] = m
        self.pendientes = pendientes_actualizados

    def obtener_clima_historico(self, lat, lon, fecha):
        try:
            url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={fecha}&end_date={fecha}&daily=temperature_2m_max&timezone=auto"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def obtener_clima_forecast(self, lat, lon):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def ejecutar_trade(self, ciudad, config):
        total_riesgo = self.obtener_capital_en_riesgo()
        cap_max_riesgo = self.data["balance"] * MAX_CLUSTER_EXPOSURE
        
        if total_riesgo >= cap_max_riesgo: return

        try:
            query = '{ markets(first: 3, where: {question_contains_nocase: "%s"}) { id question endDate outcomes { name price } volume } }' % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            markets = [m for m in res["data"]["markets"] if float(m["volume"]) >= 5000]
            
            t_forecast = self.obtener_clima_forecast(config["lat"], config["lon"])
            if not markets or t_forecast is None: return

            for mkt in markets:
                if mkt["id"] in self.pendientes: continue

                umbral, op = self.parsear_mercado_robusto(mkt["question"])
                if umbral is None: continue

                p_yes_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "yes")
                p_no_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "no")

                # MATEMÁTICA CDF CORRECTA
                z = (t_forecast - umbral) / BASE_SIGMA
                prob_gt = 0.5 * (1 + math.erf(z / math.sqrt(2)))
                
                # Probabilidad YES según operador
                prob_yes_mod = prob_gt if op == ">" else (1 - prob_gt)
                
                # Elección de lado (Arbitraje)
                if prob_yes_mod > p_yes_mkt:
                    lado, prob, precio = "YES", prob_yes_mod, p_yes_mkt
                else:
                    lado, prob, precio = "NO", (1 - prob_yes_mod), p_no_mkt

                edge = prob - precio
                if edge > EDGE_THRESHOLD:
                    disponible = self.data["balance"] - total_riesgo
                    stake = disponible * min(edge * 0.4, MAX_EVENT_EXPOSURE)
                    
                    if total_riesgo + stake > cap_max_riesgo:
                        stake = cap_max_riesgo - total_riesgo
                    
                    if stake < 1.0: continue
                    
                    win_neto = (stake * (1/precio - 1)) * (1 - COMISION_GANANCIA)
                    ev = (prob * win_neto) - ((1 - prob) * stake)

                    if ev > 0:
                        try:
                            fecha_exp = datetime.fromtimestamp(int(mkt["endDate"])).strftime('%Y-%m-%d')
                        except:
                            fecha_exp = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": prob, "precio": precio,
                            "stake": stake, "ev": ev, "umbral": umbral, "op": op,
                            "lat": config["lat"], "lon": config["lon"],
                            "win_neto": win_neto, "fecha_expiracion": fecha_exp
                        }
                        total_riesgo += stake
                        print(f"📝 Registrada: {ciudad} | {lado} | Prob: {prob:.2%}")
        except Exception as e: print(f"⚠️ Error: {e}")

    def ejecutar(self):
        self.resolver_mercados_pendientes()
        for ciudad, config in self.ciudades_config.items():
            self.ejecutar_trade(ciudad, config)

        if self.data["balance"] > self.data["peak_balance"]:
            self.data["peak_balance"] = self.data["balance"]

        self.data["historial"].append({"fecha": datetime.now().strftime("%d/%m"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]

        with open(ARCHIVO_PENDIENTES, 'w') as f: json.dump(self.pendientes, f)
        with open(ARCHIVO_BILLETERA, 'w') as f: json.dump(self.data, f)
        self.generar_dashboard()

    def generar_dashboard(self):
        color = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        riesgo = self.obtener_capital_en_riesgo()
        
        html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ background: #0f172a; color: white; font-family: sans-serif; text-align: center; padding: 20px; }}
                .balance {{ font-size: 3.5em; color: {color}; font-weight: bold; }}
                .container {{ max-width: 800px; margin: auto; background: #1e293b; padding: 20px; border-radius: 20px; }}
                .stats {{ color: #94a3b8; font-size: 0.9em; margin-top: 15px; display: flex; justify-content: space-around; border-top: 1px solid #334155; padding-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p>WEATHERTRADER QUANT v4.4</p>
                <div class="balance">${self.data['balance']:.2f}</div>
                <canvas id="c"></canvas>
                <div class="stats">
                    <span>En Riesgo: ${riesgo:.2f}</span>
                    <span>Pendientes: {len(self.pendientes)}</span>
                </div>
            </div>
            <script>
                new Chart(document.getElementById('c'), {{
                    type: 'line',
                    data: {{ labels: {json.dumps(labels)}, 
                    datasets: [{{ data: {json.dumps(valores)}, borderColor: '{color}', borderWidth: 3, tension: 0.3, pointRadius: 0, fill: false }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f: f.write(html)

if __name__ == "__main__":
    WeatherTraderV4_4().ejecutar()
