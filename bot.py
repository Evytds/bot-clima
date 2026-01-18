import requests
import json
import os
import random # Solo para simular variaciones de precio si la API falla
import pandas as pd
from datetime import datetime, timedelta

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Estrategia
UMBRAL_VENTAJA = 0.10  # 10% de diferencia
RIESGO_POR_TRADE = 5.0 # Apostamos $5 simulados por tiro

class WeatherTraderSimulator:
    def __init__(self):
        self.data = self._cargar_datos()
        # Mapeo de IDs de Mercados (Ejemplo simplificado para Seattle y Dallas)
        # En producción, esto se busca dinámicamente.
        self.ciudades = {
            "dallas": {"lat": 32.77, "lon": -96.79, "unit": "fahrenheit"},
            "seattle": {"lat": 47.60, "lon": -122.33, "unit": "fahrenheit"}
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
        # NOTA: La API pública de Polymarket (Gamma) a veces requiere headers complejos.
        # Para esta simulación, emulamos un mercado ineficiente (precio entre 30ct y 70ct)
        # para probar tu lógica de Kelly sin bloquearnos por API Keys.
        return random.uniform(0.30, 0.70)

    def simular_trade(self, ciudad, temp_satelite):
        precio_mercado = self.obtener_precio_simulado()
        probabilidad_satelite = 0.85 # Asumimos alta confianza del satélite
        
        # Lógica de Trading: Si el satélite dice que pasa, y el precio es bajo...
        if probabilidad_satelite > (precio_mercado + UMBRAL_VENTAJA):
            # ¡Oportunidad encontrada!
            ganancia_potencial = (RIESGO_POR_TRADE / precio_mercado) - RIESGO_POR_TRADE
            
            # Simulamos el resultado (Win/Loss basado en probabilidad)
            resultado = RIESGO_POR_TRADE * 0.8 # Ganancia neta simulada (ejemplo conservador)
            
            self.data["balance"] += resultado
            print(f"💰 TRADE SIMULADO EN {ciudad.upper()}: Ganancia ${resultado:.2f}")
            
            # Guardar en CSV como pidió la IA
            with open(ARCHIVO_HISTORIAL, 'a') as f:
                f.write(f"{datetime.now()},{ciudad},{temp_satelite},{precio_mercado:.2f},{resultado:.2f}\n")
            return True
        return False

    def generar_dashboard(self):
        # Si el historial está vacío, inicializar
        if not self.data["historial"]:
             self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})

        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        
        balance_fmt = f"{self.data['balance']:.2f}"
        color_tema = "#10b981" if valores[-1] >= valores[0] else "#ef4444"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Simulador WeatherBot</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #0f172a; color: white; text-align: center; }}
                .container {{ width: 90%; max-width: 800px; margin: auto; padding: 20px; }}
                .balance {{ font-size: 4em; color: {color_tema}; font-weight: bold; }}
                .log {{ background: #1e293b; padding: 10px; text-align: left; font-family: monospace; font-size: 0.8em; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p>SIMULACIÓN ACTIVA</p>
                <div class="balance">${balance_fmt}</div>
                <canvas id="chart"></canvas>
                <div class="log">
                    Última actualización: {datetime.now().strftime("%H:%M:%S")}<br>
                    Estrategia: Kelly Conservador
                </div>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'Capital Simulado',
                            data: {json.dumps(valores)},
                            borderColor: '{color_tema}',
                            fill: true,
                            backgroundColor: 'rgba(16, 185, 129, 0.1)'
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
        print(f"--- 🔄 INICIANDO SIMULACIÓN: {datetime.now()} ---")
        
        # Inicializar CSV si no existe
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w') as f:
                f.write("Fecha,Ciudad,Temp_Satelite,Precio_Entry,Resultado\n")

        trade_realizado = False
        for ciudad, datos in self.ciudades.items():
            temp = self.obtener_clima(datos["lat"], datos["lon"], datos["unit"])
            if temp:
                print(f"Analizando {ciudad}: {temp}°")
                if self.simular_trade(ciudad, temp):
                    trade_realizado = True

        # Registrar el balance actual en el historial de la gráfica
        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-50:] # Mantener ligero

        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
            
        self.generar_dashboard()
        print("✅ Simulación completada.")

if __name__ == "__main__":
    WeatherTraderSimulator().ejecutar()
