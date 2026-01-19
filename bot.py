import requests
import json
import os
import random
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Parámetros de la Estrategia (Tus Reglas v3.0)
EDGE_THRESHOLD = 0.05      # 5% de ventaja mínima para operar
MAX_PCT_BY_TRADE = 0.02    # Máximo 2% del capital por evento (Regla de Oro)
COMISION_MERCADO = 0.02    # 2% de fee
MAX_DRAWDOWN_LIMIT = 20.0  # Stop-loss global

class WeatherTraderV3:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = {
            "seoul": {"lat": 37.56, "lon": 126.97, "unit": "celsius"},
            "atlanta": {"lat": 33.74, "lon": -84.38, "unit": "fahrenheit"},
            "dallas": {"lat": 32.77, "lon": -96.79, "unit": "fahrenheit"},
            "seattle": {"lat": 47.60, "lon": -122.33, "unit": "fahrenheit"},
            "nyc": {"lat": 40.71, "lon": -74.00, "unit": "fahrenheit"},
            "london": {"lat": 51.50, "lon": -0.12, "unit": "celsius"}
        }

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    return json.load(f)
            except: pass
        return {"balance": CAPITAL_INICIAL, "historial": []}

    def obtener_clima(self, lat, lon, unit):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unit}&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def obtener_precio_polymarket(self, ciudad):
        """
        Simula la entrada de la API de Polymarket. 
        En la v3.1 conectaremos el Subgraph de The Graph aquí.
        """
        return random.uniform(0.35, 0.65)

    def calcular_probabilidad_modelo(self, temp, unidad):
        # Tu lógica de certeza climática
        temp_f = temp if unidad == "fahrenheit" else (temp * 9/5) + 32
        if temp_f > 90 or temp_f < 35: return 0.75
        elif temp_f > 80 or temp_f < 45: return 0.65
        else: return 0.52

    def detectar_edge(self, prob_real, precio_mercado):
        # precio_mercado funciona como la probabilidad implícita
        edge = prob_real - precio_mercado
        if edge > EDGE_THRESHOLD:
            return "YES", edge
        elif edge < -EDGE_THRESHOLD:
            return "NO", abs(edge)
        return None, 0

    def calcular_ev(self, prob_real, precio_mercado, stake):
        # Esperanza Matemática: E = (P * W) - (Q * L)
        p_ganar = prob_real
        p_perder = 1 - prob_real
        ganancia_posible = (stake / precio_mercado) - stake
        ev = (p_ganar * ganancia_posible) - (p_perder * stake)
        return ev

    def ejecutar_trade(self, ciudad, temp, unidad):
        precio_mercado = self.obtener_precio_polymarket(ciudad)
        prob_real = self.calcular_probabilidad_modelo(temp, unidad)
        
        lado, edge = self.detectar_edge(prob_real, precio_mercado)
        
        if lado:
            # Position Sizing: min(edge, max_pct)
            fraccion_riesgo = min(edge, MAX_PCT_BY_TRADE)
            stake = self.data["balance"] * fraccion_riesgo
            
            if stake < 1.0: return False # Ignorar trades insignificantes

            ev_esperado = self.calcular_ev(prob_real, precio_mercado, stake)
            
            # Simulación de resultado (Monte Carlo)
            ganancia_neta = 0
            resultado = ""
            if random.random() < prob_real:
                neto_con_fees = (stake / precio_mercado) * (1 - COMISION_MERCADO)
                ganancia_neta = neto_con_fees - stake
                resultado = "WIN"
            else:
                ganancia_neta = -stake
                resultado = "LOSS"

            self.data["balance"] += ganancia_neta
            print(f"📊 {ciudad.upper()} | Edge: {edge:.2%} | EV: ${ev_esperado:.2f} | {resultado}: ${ganancia_neta:.2f}")
            
            with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
                # Log extendido para auditoría profesional
                f.write(f"{datetime.now()},{ciudad},{prob_real:.2f},{precio_mercado:.2f},{edge:.2f},{stake:.2f},{ev_esperado:.2f},{ganancia_neta:.2f}\n")
            return True
        return False

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        color = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"

        html = f"""
        <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ background: #0f172a; color: white; font-family: sans-serif; text-align: center; }}
                .balance {{ font-size: 4em; color: {color}; font-weight: bold; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 15px; width: 80%; margin: 20px auto; }}
            </style>
        </head>
        <body>
            <p>WEATHERTRADER V3.0 ENGINE</p>
            <div class="balance">${self.data['balance']:.2f}</div>
            <div class="card"><canvas id="c"></canvas></div>
            <script>
                new Chart(document.getElementById('c'), {{
                    type: 'line',
                    data: {{ labels: {json.dumps(labels)}, 
                    datasets: [{{ data: {json.dumps(valores)}, borderColor: '{color}', tension: 0.4 }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        if self.data["balance"] < MAX_DRAWDOWN_LIMIT: return
        
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Prob_Real,Precio,Edge,Stake,EV,Resultado\n")

        for ciudad, datos in self.ciudades.items():
            temp = self.obtener_clima(datos["lat"], datos["lon"], datos["unit"])
            if temp is not None:
                self.ejecutar_trade(ciudad, temp, datos["unit"])

        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-50:]
        with open(ARCHIVO_BILLETERA, 'w') as f: json.dump(self.data, f)
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderV3().ejecutar()
