import requests
import json
import os
import random
import re
import math
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN QUANT v3.5 ===
# Usamos tu balance actual reportado
CAPITAL_INICIAL = 196.70 
# Error estándar del pronóstico a 24h (en °C). 1.5 es un estándar industrial.
SIGMA_METEO = 1.5         
EDGE_THRESHOLD = 0.06     # 6% de ventaja mínima para compensar error de modelo
MAX_EVENT_EXPOSURE = 0.03 # Máximo 3% del capital por evento
COMISION_GANANCIA = 0.02  # Fee de Polymarket sobre el profit
STOP_LOSS_ABSOLUTO = 50.0 # Si bajamos de $50, el bot se detiene

ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

class WeatherTraderV3_5:
    def __init__(self):
        self.data = self._cargar_datos()
        # Coordenadas precisas para el modelo matemático
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

    def obtener_clima(self, lat, lon):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def parsear_condicion_mercado(self, pregunta):
        """
        Extrae el umbral numérico y el sentido de la apuesta (arriba/abajo).
        Ej: 'Will Seattle exceed 25°C?' -> (25.0, '>')
        """
        try:
            # Extraer el primer número (punto decimal opcional)
            match_num = re.search(r"[-+]?\d*\.\d+|\d+", pregunta)
            if not match_num: return None, None
            threshold = float(match_num.group())
            
            # Lógica de detección de operador
            op = ">" # Por defecto
            if any(word in pregunta.lower() for word in ["below", "under", "lower", "less"]):
                op = "<"
            return threshold, op
        except: return None, None

    def calcular_probabilidad_gaussiana(self, pronostico, umbral, operador):
        """
        Calcula la probabilidad de que ocurra el evento usando la 
        Función de Distribución Acumulada (CDF) de una Normal.
        """
        # Distancia al umbral normalizada por el error estándar (Z-score)
        z = (umbral - pronostico) / (SIGMA_METEO * math.sqrt(2))
        phi = 0.5 * (1 + math.erf(z))
        
        if operador == ">":
            return 1 - phi # Probabilidad de estar por encima
        else:
            return phi     # Probabilidad de estar por debajo

    def obtener_precios_polymarket(self, ciudad):
        try:
            query = '{ markets(first: 5, where: {question_contains_nocase: "%s"}) { question outcomes { name price } volume } }' % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            # Filtrar mercados con liquidez real (> $5,000)
            return [m for m in res["data"]["markets"] if float(m["volume"]) >= 5000]
        except: return []

    def ejecutar_trade(self, ciudad, config):
        mercados = self.obtener_precios_polymarket(ciudad)
        pronostico = self.obtener_clima(config["lat"], config["lon"])
        
        if not mercados or pronostico is None: return

        for mkt in mercados:
            pregunta = mkt["question"]
            umbral, op = self.parsear_condicion_mercado(pregunta)
            
            if umbral is None: continue

            # Precios de mercado
            p_yes_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "yes")
            p_no_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "no")

            # Cálculo estadístico de probabilidad real
            prob_yes_mod = self.calcular_probabilidad_gaussiana(pronostico, umbral, op)
            prob_no_mod = 1 - prob_yes_mod

            # Detección de Edge (Ventaja)
            edge_yes = prob_yes_mod - p_yes_mkt
            edge_no = prob_no_mod - p_no_mkt

            if edge_yes > EDGE_THRESHOLD:
                self.procesar_resultado(ciudad, "YES", prob_yes_mod, p_yes_mkt, edge_yes, pregunta)
            elif edge_no > EDGE_THRESHOLD:
                self.procesar_resultado(ciudad, "NO", prob_no_mod, p_no_mkt, edge_no, pregunta)

    def procesar_resultado(self, ciudad, lado, prob, precio, edge, pregunta):
        # Position Sizing: 3% cap con ajuste por ventaja
        stake = self.data["balance"] * min(edge * 0.5, MAX_EVENT_EXPOSURE)
        if stake < 1.0: return

        # Win Neto (Fees solo en profit)
        win_bruto = stake * (1/precio - 1)
        win_neto = win_bruto * (1 - COMISION_GANANCIA)
        ev_neto = (prob * win_neto) - ((1 - prob) * stake)

        if ev_neto <= 0: return

        # Simulación de resultado (Paper Trading)
        if random.random() < prob:
            res_dinero = win_neto
            tipo = "WIN"
        else:
            res_dinero = -stake
            tipo = "LOSS"

        self.data["balance"] += res_dinero
        if self.data["balance"] > self.data["peak_balance"]:
            self.data["peak_balance"] = self.data["balance"]

        # Log de Auditoría
        with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now()},{ciudad},{lado},{prob:.2f},{precio:.2f},{stake:.2f},{ev_neto:.2f},{res_dinero:.2f}\n")
        
        print(f"🎯 {ciudad}: {lado} en '{pregunta[:30]}...' | EV: ${ev_neto:.2f} | {tipo}: ${res_dinero:.2f}")

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
                .balance {{ font-size: 4em; color: {color}; font-weight: bold; }}
                .container {{ max-width: 800px; margin: auto; background: #1e293b; padding: 20px; border-radius: 20px; }}
                .stats {{ color: #94a3b8; font-size: 0.9em; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p>WEATHERTRADER V3.5 (GAUSSIAN ENGINE)</p>
                <div class="balance">${self.data['balance']:.2f}</div>
                <canvas id="c"></canvas>
                <div class="stats">Max Drawdown: {dd:.2f}% | Mode: Quant Arbitrage</div>
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
        if self.data["balance"] < STOP_LOSS_ABSOLUTO: return
        
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Lado,Prob,Precio,Stake,EV,Resultado\n")

        # Ejecución en serie por ciudades
        for ciudad, config in self.ciudades_config.items():
            self.ejecutar_trade(ciudad, config)

        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f: json.dump(self.data, f)
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderV3_5().ejecutar()
