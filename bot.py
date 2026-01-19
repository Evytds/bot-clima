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

# Parámetros de Seguridad
KELLY_FRACTION = 0.25  # Kelly Conservador (Usamos solo un cuarto del Kelly Full)
MAX_DRAWDOWN_LIMIT = 20.0 # Si el balance baja de $20, el bot se apaga por seguridad

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
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def obtener_precio_simulado(self):
        # Simula ineficiencias del mercado (Precios entre 35 y 65 centavos)
        return random.uniform(0.35, 0.65)

    def calcular_probabilidad_real(self, temp, unidad):
        # Lógica: Las temperaturas extremas son más fáciles de predecir que las medias.
        # Esto asigna una "Confianza del Satélite" basada en el dato.
        
        # Normalizar a Fahrenheit para el cálculo
        temp_f = temp if unidad == "fahrenheit" else (temp * 9/5) + 32
        
        # Si hace mucho calor (>90F) o mucho frío (<40F), el satélite tiene alta certeza
        if temp_f > 90 or temp_f < 40:
            return 0.85 # 85% de certeza
        elif temp_f > 80 or temp_f < 50:
            return 0.70 # 70% de certeza
        else:
            return 0.55 # Zona gris (55%), difícil de predecir

    def calcular_kelly(self, probabilidad, precio_mercado):
        # Fórmula de Kelly: f = (p/q) - (1-p)/q  Donde q es el precio (odds)
        # Simplificado para binarias: f = (p - precio) / (1 - precio)
        # Nota: Precio mercado actúa como probabilidad implícita
        
        if precio_mercado >= 1: return 0 # Evitar división por cero
        
        edge = probabilidad - precio_mercado
        if edge <= 0: return 0 # No hay ventaja, no apostar
        
        kelly_full = edge / (1 - precio_mercado)
        return max(0, kelly_full) # Nunca devolver negativo

    def simular_trade(self, ciudad, temp, unidad):
        # 1. Obtener datos
        precio_mercado = self.obtener_precio_simulado()
        probabilidad_real = self.calcular_probabilidad_real(temp, unidad)
        
        # 2. Calcular Tamaño de Apuesta (Kelly)
        fraccion_kelly = self.calcular_kelly(probabilidad_real, precio_mercado)
        fraccion_segura = fraccion_kelly * KELLY_FRACTION # Aplicamos factor conservador
        
        stake = self.data["balance"] * fraccion_segura
        
        # Filtros de seguridad (No apostar centavos, ni apuestas suicidas)
        if stake < 1.0 or stake > (self.data["balance"] * 0.2):
            return False 

        # 3. Simulación Estadística Honesta (Monte Carlo)
        # Aquí lanzamos el dado basado en la PROBABILIDAD REAL, no un 0.8 fijo.
        ganancia_neta = 0
        tipo = ""
        
        if random.random() < probabilidad_real:
            # GANAMOS: El pago es (1 / precio) - 1
            retorno = (stake / precio_mercado) - stake
            ganancia_neta = retorno
            tipo = "WIN"
        else:
            # PERDEMOS
            ganancia_neta = -stake
            tipo = "LOSS"

        # 4. Actualizar Balance
        self.data["balance"] += ganancia_neta
        print(f"🎲 {ciudad.upper()}: Stake ${stake:.2f} (Prob {probabilidad_real*100:.0f}% vs Precio {precio_mercado:.2f}) -> {tipo} ${ganancia_neta:.2f}")
        
        # 5. Guardar CSV (Con encoding UTF-8 explícito como pidió la IA)
        with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now()},{ciudad},{temp},{probabilidad_real:.2f},{precio_mercado:.2f},{stake:.2f},{ganancia_neta:.2f}\n")
        return True

    def generar_dashboard(self):
        if not self.data["historial"]:
             self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})

        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        balance_fmt = f"{self.data['balance']:.2f}"
        
        color_tema = "#10b981"
        if len(valores) >= 2 and valores[-1] < valores[-2]: color_tema = "#ef4444"

        ciudades_html = "".join([f'<span class="city-tag">{c.upper()}</span>' for c in self.ciudades.keys()])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Elite Math Simulator</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #0f172a; color: white; text-align: center; margin: 0; }}
                .container {{ width: 95%; max-width: 800px; margin: auto; padding: 20px; }}
                .balance {{ font-size: 4em; color: {color_tema}; font-weight: bold; margin: 10px 0; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 15px; margin-top: 20px; }}
                .city-tag {{ display: inline-block; background: #334155; padding: 5px 10px; border-radius: 5px; margin: 5px; font-size: 0.8em; color: #94a3b8; font-weight: bold; }}
                .badge {{ background: #3b82f6; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.7em; vertical-align: middle; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p style="color: #94a3b8;">CAPITAL MATEMÁTICO <span class="badge">KELLY V2</span></p>
                <div class="balance">${balance_fmt}</div>
                <div class="card"><canvas id="chart"></canvas></div>
                <div class="card"><p style="color: #94a3b8;">RANGO ACTIVO</p>{ciudades_html}</div>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'Equity Curve',
                            data: {json.dumps(valores)},
                            borderColor: '{color_tema}',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.1
                        }}]
                    }},
                    options: {{ scales: {{ x: {{ display: false }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 🧮 CICLO MATEMÁTICO REAL: {datetime.now()} ---")
        
        # Stop-Loss Global (Drawdown Control)
        if self.data["balance"] < MAX_DRAWDOWN_LIMIT:
            print(f"⚠️ SISTEMA PAUSADO: Balance bajo (${self.data['balance']}). Requiere recarga.")
            return

        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Temp,Prob_Real,Precio,Stake,Resultado\n")

        for ciudad, datos in self.ciudades.items():
            temp = self.obtener_clima(datos["lat"], datos["lon"], datos["unit"])
            if temp:
                self.simular_trade(ciudad, temp, datos["unit"])

        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-50:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderElite().ejecutar()
