import requests
import json
import os
import random
import re
import math
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN CIENTÍFICA v3.7 ===
CAPITAL_INICIAL = 196.70
BASE_SIGMA = 1.3          # Desviación estándar (error) del pronóstico en °C
EDGE_THRESHOLD = 0.07     # Ventaja mínima del 7% para disparar
MAX_EVENT_EXPOSURE = 0.02 # Máximo 2% de capital por cada trade
MAX_CYCLE_EXPOSURE = 0.05 # Máximo 5% de riesgo total por cada ejecución
COMISION_GANANCIA = 0.02  # Fee de Polymarket
PAPER_MODE = True         # True: Simula resultados / False: Solo registra trades

ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

class WeatherTraderV3_7:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades_config = {
            "Seoul": {"lat": 37.56, "lon": 126.97},
            "Atlanta": {"lat": 33.74, "lon": -84.38},
            "Dallas": {"lat": 32.77, "lon": -96.79},
            "Seattle": {"lat": 47.60, "lon": -122.33},
            "New York": {"lat": 40.71, "lon": -74.00},
            "London": {"lat": 51.50, "lon": -0.12}
        }
        self.poly_url = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"
        self.current_cycle_stake = 0 

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    d = json.load(f)
                    d.setdefault("peak_balance", d["balance"])
                    d.setdefault("historial", [])
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def obtener_clima(self, lat, lon):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def parsear_mercado(self, pregunta):
        if not any(k in pregunta.lower() for k in ["temp", "temperature", "degrees", "celsius"]):
            return None, None
        try:
            numeros = re.findall(r"[-+]?\d*\.\d+|\d+", pregunta)
            if not numeros: return None, None
            threshold = float(numeros[0])
            op = "<" if any(w in pregunta.lower() for w in ["below", "under", "less", "lower"]) else ">"
            return threshold, op
        except: return None, None

    def calcular_prob_gaussiana(self, forecast, umbral, operador):
        # Aplicamos la CDF de la Normal
        z = (umbral - forecast) / (BASE_SIGMA * math.sqrt(2))
        phi = 0.5 * (1 + math.erf(z))
        return (1 - phi) if operador == ">" else phi

    def ejecutar_trade(self, ciudad, config):
        # Límite de exposición del ciclo (Cluster Cap)
        if self.current_cycle_stake >= (self.data["balance"] * MAX_CYCLE_EXPOSURE):
            return

        try:
            query = '{ markets(first: 3, where: {question_contains_nocase: "%s"}) { question outcomes { name price } volume } }' % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            mercados = [m for m in res["data"]["markets"] if float(m["volume"]) >= 5000]
            
            t_forecast = self.obtener_clima(config["lat"], config["lon"])
            if not mercados or t_forecast is None: return

            for mkt in mercados:
                umbral, op = self.parsear_mercado(mkt["question"])
                if umbral is None: continue

                p_yes_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "yes")
                p_no_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "no")

                prob_yes_mod = self.calcular_prob_gaussiana(t_forecast, umbral, op)
                
                # Evaluación de Lado
                if prob_yes_mod > p_yes_mkt:
                    lado, prob, precio = "YES", prob_yes_mod, p_yes_mkt
                else:
                    lado, prob, precio = "NO", (1 - prob_yes_mod), p_no_mkt

                edge = prob - precio
                if edge > EDGE_THRESHOLD:
                    self.procesar(ciudad, lado, prob, precio, edge, mkt["question"])
        except: pass

    def procesar(self, ciudad, lado, prob, precio, edge, pregunta):
        # Position Sizing
        stake = self.data["balance"] * min(edge * 0.4, MAX_EVENT_EXPOSURE)
        
        # Ajuste de seguridad para no exceder el ciclo
        if self.current_cycle_stake + stake > (self.data["balance"] * MAX_CYCLE_EXPOSURE):
            stake = (self.data["balance"] * MAX_CYCLE_EXPOSURE) - self.current_cycle_stake
        
        if stake < 1.0: return

        # Win Neto (Fees solo en profit)
        win_neto = (stake * (1/precio - 1)) * (1 - COMISION_GANANCIA)
        ev_neto = (prob * win_neto) - ((1 - prob) * stake)

        if ev_neto > 0:
            self.current_cycle_stake += stake
            
            # Validación Científica (Brier Score)
            outcome_real = 1 if (random.random() < prob and PAPER_MODE) else 0
            res_dinero = win_neto if outcome_real == 1 else -stake
            brier_comp = (prob - outcome_real) ** 2

            self.data["balance"] += res_dinero
            
            with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()},{ciudad},{lado},{prob:.4f},{precio:.2f},{stake:.2f},{ev_neto:.2f},{res_dinero:.2f},{brier_comp:.4f}\n")
            
            print(f"🎯 TRADE: {ciudad} | Edge: {edge:.2%} | EV: ${ev_neto:.2f}")

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        color = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"
        dd = (self.data["peak_balance"] - self.data["balance"]) / self.data["peak_balance"] * 100

        html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ background: #0f172a; color: white; font-family: sans-serif; text-align: center; padding: 20px; }}
                .balance {{ font-size: 3.5em; color: {color}; font-weight: bold; }}
                .container {{ max-width: 800px; margin: auto; background: #1e293b; padding: 20px; border-radius: 20px; }}
                .stats {{ color: #94a3b8; font-size: 0.8em; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p>WEATHERTRADER V3.7 (SCIENTIFIC VALIDATION)</p>
                <div class="balance">${self.data['balance']:.2f}</div>
                <canvas id="c"></canvas>
                <div class="stats">Max DD: {dd:.2f}% | Mode: {"PAPER" if PAPER_MODE else "LIVE"}</div>
            </div>
            <script>
                new Chart(document.getElementById('c'), {{
                    type: 'line',
                    data: {{ labels: {json.dumps(labels)}, 
                    datasets: [{{ data: {json.dumps(valores)}, borderColor: '{color}', tension: 0.3, pointRadius: 0, fill: false }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f: f.write(html)

    def ejecutar(self):
        # Reinicio de exposición del ciclo
        self.current_cycle_stake = 0
        
        if self.data["balance"] < 25.0: return # Kill-switch

        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Lado,Prob,Precio,Stake,EV,Resultado,Brier_Comp\n")

        ciudades = list(self.ciudades_config.items())
        random.shuffle(ciudades)
        for ciudad, config in ciudades:
            self.ejecutar_trade(ciudad, config)

        if self.data["balance"] > self.data["peak_balance"]:
            self.data["peak_balance"] = self.data["balance"]

        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]
        
        with open(ARCHIVO_BILLETERA, 'w', encoding='utf-8') as f:
            json.dump(self.data, f)
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderV3_7().ejecutar()
