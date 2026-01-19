import requests
import json
import os
import random
import pandas as pd
from datetime import datetime, timedelta

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Parámetros de Riesgo y Realismo
KELLY_FRACTION = 0.25  
MAX_DRAWDOWN_LIMIT = 20.0 
COMISION_MERCADO = 0.02 # 2% de fee por trade ganado (Spread/Comisión)
MAX_TRADES_POR_CICLO = 3 # Límite para no apostar todo de golpe

class WeatherTraderElite:
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
            # FIX: Usamos [0] directamente, pero validamos None al recibir
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def obtener_precio_simulado(self):
        return random.uniform(0.35, 0.65)

    def calcular_probabilidad_real(self, temp, unidad):
        # AJUSTE REALISTA: Probabilidades más conservadoras
        temp_f = temp if unidad == "fahrenheit" else (temp * 9/5) + 32
        
        if temp_f > 90 or temp_f < 35:
            return 0.75 # Bajado de 0.85 (Más realista)
        elif temp_f > 80 or temp_f < 45:
            return 0.65 # Bajado de 0.70
        else:
            return 0.52 # Apenas mejor que una moneda al aire (Zona de incertidumbre)

    def calcular_kelly(self, probabilidad, precio_mercado):
        if precio_mercado >= 1: return 0 
        edge = probabilidad - precio_mercado
        if edge <= 0: return 0 
        kelly_full = edge / (1 - precio_mercado)
        return max(0, kelly_full) 

    def simular_trade(self, ciudad, temp, unidad):
        precio_mercado = self.obtener_precio_simulado()
        probabilidad_real = self.calcular_probabilidad_real(temp, unidad)
        
        # Kelly
        fraccion_kelly = self.calcular_kelly(probabilidad_real, precio_mercado)
        fraccion_segura = fraccion_kelly * KELLY_FRACTION 
        stake = self.data["balance"] * fraccion_segura
        
        # Filtros de seguridad
        if stake < 1.0 or stake > (self.data["balance"] * 0.15): # Bajado riesgo max al 15%
            return False 

        # Simulación con Fees
        ganancia_neta = 0
        tipo = ""
        
        if random.random() < probabilidad_real:
            # GANAMOS: (Retorno bruto * (1 - comision)) - stake
            bruto = (stake / precio_mercado)
            neto = bruto * (1 - COMISION_MERCADO)
            ganancia_neta = neto - stake
            tipo = "WIN"
        else:
            # PERDEMOS
            ganancia_neta = -stake
            tipo = "LOSS"

        self.data["balance"] += ganancia_neta
        print(f"🎲 {ciudad.upper()}: Stake ${stake:.2f} (Prob {probabilidad_real*100:.0f}%) -> {tipo} ${ganancia_neta:.2f}")
        
        with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now()},{ciudad},{temp},{probabilidad_real:.2f},{precio_mercado:.2f},{stake:.2f},{ganancia_neta:.2f}\n")
        return True

    def generar_dashboard(self):
        if not self.data["historial"]:
             self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})

        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        
        # FIX VISUAL: Compara contra Capital Inicial Global
        color_tema = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"

        ciudades_html = "".join([f'<span class="city-tag">{c.upper()}</span>' for c in self.ciudades.keys()])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Elite Math Simulator V2</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #0f172a; color: white; text-align: center; margin: 0; }}
                .container {{ width: 95%; max-width: 800px; margin: auto; padding: 20px; }}
                .balance {{ font-size: 4em; color: {color_tema}; font-weight: bold; margin: 10px 0; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 15px; margin-top: 20px; }}
                .city-tag {{ display: inline-block; background: #334155; padding: 5px 10px; border-radius: 5px; margin: 5px; font-size: 0.8em; color: #94a3b8; font-weight: bold; }}
                .stats {{ display: flex; justify-content: space-around; margin-top: 10px; color: #94a3b8; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p style="color: #94a3b8;">CAPITAL NETO (POST-FEES)</p>
                <div class="balance">${self.data['balance']:.2f}</div>
                
                <div class="card">
                    <canvas id="chart"></canvas>
                </div>
                
                <div class="card">
                    <p style="color: #94a3b8;">RADAR ACTIVO</p>
                    {ciudades_html}
                </div>

                <div class="stats">
                    <span>Fee: 2%</span>
                    <span>Max Trades: 3/ciclo</span>
                    <span>Kelly: 0.25</span>
                </div>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'Equity',
                            data: {json.dumps(valores)},
                            borderColor: '{color_tema}',
                            backgroundColor: 'rgba(125, 125, 125, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0
                        }}]
                    }},
                    options: {{ 
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }}
                    }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 🧮 CICLO V2 (FEES + REALISMO): {datetime.now()} ---")
        
        if self.data["balance"] < MAX_DRAWDOWN_LIMIT:
            print(f"⛔ STOP-LOSS ACTIVADO: Balance ${self.data['balance']}")
            return

        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Temp,Prob_Real,Precio,Stake,Resultado\n")

        trades_hoy = 0
        ciudades_random = list(self.ciudades.items())
        random.shuffle(ciudades_random) # Mezclar para no priorizar siempre a Seoul por orden alfabético

        for ciudad, datos in ciudades_random:
            if trades_hoy >= MAX_TRADES_POR_CICLO:
                print("⏳ Límite de trades por ciclo alcanzado.")
                break

            temp = self.obtener_clima(datos["lat"], datos["lon"], datos["unit"])
            
            # FIX 1: Validación robusta de temperatura (Cero no es False)
            if temp is not None:
                trade_hecho = self.simular_trade(ciudad, temp, datos["unit"])
                if trade_hecho:
                    trades_hoy += 1

        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-50:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        
        self.generar_dashboard()
        print("✅ Ciclo completado.")

if __name__ == "__main__":
    WeatherTraderElite().ejecutar()
