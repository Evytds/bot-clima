import requests
import json
import os
import re
import math
import pandas as pd
from datetime import datetime, timedelta

# === CONFIGURACIÓN QUANT v4.8 ===
CAPITAL_INICIAL = 196.70
BASE_SIGMA = 1.3          # Desviación estándar base
EDGE_THRESHOLD = 0.07     # Umbral de ventaja mínima
MAX_EVENT_EXPOSURE = 0.02 # 2% por trade
MAX_CLUSTER_EXPOSURE = 0.05 # 5% riesgo total acumulado
COMISION_GANANCIA = 0.02

POLY_URL = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"

class WeatherTraderV4_8:
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

    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json", 'r') as f:
                    d = json.load(f)
                    d.setdefault("peak_balance", d["balance"])
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def _cargar_pendientes(self):
        if os.path.exists("mercados_pendientes.json"):
            try:
                with open("mercados_pendientes.json", 'r') as f: return json.load(f)
            except: pass
        return {}

    def obtener_capital_en_riesgo(self):
        return sum(m['stake'] for m in self.pendientes.values())

    def parsear_mercado_robusto(self, pregunta):
        match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", pregunta, re.IGNORECASE)
        if match:
            threshold = float(match.group(1))
            unidad = match.group(2).lower()
            if unidad in ["f", "fahrenheit"]:
                threshold = (threshold - 32) * 5/9
        else:
            nums = re.findall(r"[-+]?\d*\.?\d+", pregunta)
            if not nums: return None, None
            threshold = float(nums[0])
        
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
                    
                    res_dinero = m['win_neto'] if gano else -m['stake']
                    brier_comp = (m['prob'] - (1 if gano else 0)) ** 2

                    self.data["balance"] += res_dinero
                    
                    # Log extendido con Sigma para auditoría
                    with open("historial_ganancias.csv", 'a', encoding='utf-8') as f:
                        f.write(f"{datetime.now()},{m['ciudad']},{m['lado']},{m['prob']:.4f},{m['precio']:.2f},{m['stake']:.2f},{res_dinero:.2f},{brier_comp:.4f},{m.get('t_forecast',0):.2f},{t_real:.2f},{m.get('sigma',0):.2f}\n")
                else:
                    pendientes_actualizados[m_id] = m
            else:
                pendientes_actualizados[m_id] = m
        self.pendientes = pendientes_actualizados

    def obtener_clima_historico(self, lat, lon, fecha):
        try:
            url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={fecha}&end_date={fecha}&daily=temperature_2m_max&timezone=auto"
            res = requests.get(url, timeout=10).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def ejecutar_trade(self, ciudad, config):
        if any(m["ciudad"] == ciudad for m in self.pendientes.values()):
            return

        total_riesgo = self.obtener_capital_en_riesgo()
        cap_max_riesgo = self.data["balance"] * MAX_CLUSTER_EXPOSURE
        if total_riesgo >= cap_max_riesgo: return

        query = '{ markets(first: 3, where: {question_contains_nocase: "%s"}) { id question endDate outcomes { name price } volume } }' % ciudad
        
        try:
            response = requests.post(POLY_URL, json={"query": query}, timeout=15)
            res = response.json()
            if "errors" in res or "data" not in res or "markets" not in res["data"]: return

            markets = [m for m in res["data"]["markets"] if float(m.get("volume", 0)) >= 5000]
            if not markets: return

            try:
                url_f = f"https://api.open-meteo.com/v1/forecast?latitude={config['lat']}&longitude={config['lon']}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
                f_res = requests.get(url_f, timeout=10).json()
                t_forecast = f_res['daily']['temperature_2m_max'][0]
            except: return

            for mkt in markets:
                if mkt["id"] in self.pendientes: continue
                umbral, op = self.parsear_mercado_robusto(mkt["question"])
                if umbral is None: continue

                try:
                    p_yes_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "yes")
                    p_no_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "no")
                except: continue

                # 📐 Matemática Institucional
                z = (t_forecast - umbral) / BASE_SIGMA
                prob_gt = 0.5 * (1 + math.erf(z / math.sqrt(2)))
                prob_yes_mod = prob_gt if op == ">" else (1 - prob_gt)
                
                # 🔧 MEJORA 1: Clamp de probabilidad (Robustez numérica)
                prob_yes_mod = max(0.001, min(0.999, prob_yes_mod))
                
                lado, prob, precio = ("YES", prob_yes_mod, p_yes_mkt) if prob_yes_mod > p_yes_mkt else ("NO", (1 - prob_yes_mod), p_no_mkt)

                edge = prob - precio
                if edge > EDGE_THRESHOLD:
                    # Cash vs Equity management
                    disponible = self.data["balance"] - total_riesgo
                    stake = disponible * min(edge * 0.4, MAX_EVENT_EXPOSURE)
                    if total_riesgo + stake > cap_max_riesgo: stake = cap_max_riesgo - total_riesgo
                    if stake < 1.0: continue
                    
                    win_neto = (stake * (1/precio - 1)) * (1 - COMISION_GANANCIA)
                    ev = (prob * win_neto) - ((1 - prob) * stake)

                    if ev > 0:
                        try:
                            fecha_exp = datetime.fromtimestamp(int(mkt["endDate"])).strftime('%Y-%m-%d')
                        except:
                            fecha_exp = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

                        # 🔧 MEJORA 2: Logging de parámetros (Sigma)
                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": prob, "precio": precio,
                            "stake": stake, "umbral": umbral, "op": op,
                            "lat": config["lat"], "lon": config["lon"],
                            "win_neto": win_neto, "fecha_expiracion": fecha_exp,
                            "t_forecast": t_forecast,
                            "sigma": BASE_SIGMA,
                            "ev": ev
                        }
                        total_riesgo += stake
                        print(f"📊 Trade: {ciudad} | Prob: {prob:.1%} | Sigma: {BASE_SIGMA}")

        except Exception as e: print(f"⚠️ API Error: {type(e).__name__}")

    def generar_dashboard(self):
        riesgo = self.obtener_capital_en_riesgo()
        cash = self.data["balance"] - riesgo
        color = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        
        html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ background: #0f172a; color: white; font-family: sans-serif; text-align: center; padding: 20px; }}
                .balance {{ font-size: 4em; color: {color}; font-weight: bold; margin: 0; }}
                .container {{ max-width: 850px; margin: auto; background: #1e293b; padding: 25px; border-radius: 24px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); }}
                .stats {{ color: #94a3b8; font-size: 0.9em; margin-top: 20px; display: flex; justify-content: space-around; border-top: 1px solid #334155; padding-top: 20px; }}
                .label {{ display: block; color: #64748b; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.05em; }}
                .value {{ font-size: 1.2em; color: white; font-weight: 600; }}
            </style>
        </head>
        <body>
            <div class="container">
                <span class="label">Total Equity (USD)</span>
                <div class="balance">${self.data['balance']:.2f}</div>
                <canvas id="c" style="max-height: 300px; margin: 20px 0;"></canvas>
                <div class="stats">
                    <div><span class="label">Available Cash</span><span class="value">${cash:.2f}</span></div>
                    <div><span class="label">At Risk</span><span class="value">${riesgo:.2f}</span></div>
                    <div><span class="label">Active Markets</span><span class="value">{len(self.pendientes)}</span></div>
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
        with open("index.html", 'w', encoding='utf-8') as f: f.write(html)

    def ejecutar(self):
        self.resolver_mercados_pendientes()
        ciudades = list(self.ciudades_config.items())
        import random
        random.shuffle(ciudades)
        for ciudad, config in ciudades: self.ejecutar_trade(ciudad, config)

        if self.data["balance"] > self.data["peak_balance"]: self.data["peak_balance"] = self.data["balance"]
        self.data["historial"].append({"fecha": datetime.now().strftime("%d/%m"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]

        with open("mercados_pendientes.json", 'w') as f: json.dump(self.pendientes, f)
        with open("billetera_virtual.json", 'w') as f: json.dump(self.data, f)
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderV4_8().ejecutar()
