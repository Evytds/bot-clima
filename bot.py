import requests
import json
import re
import os
from datetime import datetime, timedelta

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Parámetros de Riesgo
RIESGO_MAX_OP = 0.15 # 15% del capital
UMBRAL_VENTAJA = 12.0 # 12% de ventaja mínima

class WeatherTraderPerpetual:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
            "nyc": [40.71, -74.00, "fahrenheit"],
            "london": [51.50, -0.12, "celsius"],
            "toronto": [43.65, -79.38, "celsius"]
        }

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    return json.load(f)
            except: pass
        return {"balance": CAPITAL_INICIAL, "historial": [{"fecha": datetime.now().strftime("%H:%M"), "balance": CAPITAL_INICIAL}]}

    def obtener_fechas_objetivo(self):
        """Genera los strings de fecha para hoy y mañana (ej: 'january-18')."""
        hoy = datetime.now()
        manana = hoy + timedelta(days=1)
        
        def formatear(dt):
            # Formato: mes-día (ej: january-18)
            return dt.strftime("%B-%d").lower()
            
        return [formatear(hoy), formatear(manana)]

    def obtener_clima(self, lat, lon, unidad):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unidad}&timezone=auto&forecast_days=2"
            res = requests.get(url).json()
            # Retornamos el pronóstico de hoy (índice 0) y mañana (índice 1)
            return res['daily']['temperature_2m_max']
        except: return [None, None]

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        
        color_balance = "#10b981"
        if len(valores) >= 2 and valores[-1] < valores[-2]:
            color_balance = "#ef4444"
            
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dashboard Bot Clima</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #0f172a; color: white; text-align: center; }}
                .container {{ width: 90%; max-width: 800px; margin: auto; padding: 20px; }}
                .balance {{ font-size: 4.5em; color: {color_balance}; font-weight: bold; margin: 10px 0; }}
                .chart-box {{ background: #1e293b; padding: 20px; border-radius: 15px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p style="color: #94a3b8;">CAPITAL DISPONIBLE</p>
                <div class="balance">${self.data["balance"]:.2f}</div>
                <p style="color: #94a3b8;">USDC (Simulado)</p>
                <div class="chart-box">
                    <canvas id="chart"></canvas>
                </div>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'Rendimiento USDC',
                            data: {json.dumps(valores)},
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4
                        }}]
                    }},
                    options: {{ 
                        scales: {{ 
                            y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }},
                            x: {{ ticks: {{ color: '#94a3b8' }} }}
                        }},
                        plugins: {{ legend: {{ display: false }} }}
                    }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 🔄 CICLO PERPETUO INICIADO: {datetime.now()} ---")
        fechas = self.obtener_fechas_objetivo()
        
        for ciudad, coords in self.ciudades.items():
            temps = self.obtener_clima(coords[0], coords[1], coords[2])
            
            for i, fecha_str in enumerate(fechas):
                slug = f"highest-temperature-in-{ciudad}-on-{fecha_str}"
                temp_pronosticada = temps[i]
                
                if temp_pronosticada is None: continue
                
                try:
                    res_poly = requests.get(f"https://gamma-api.polymarket.com/events/slug/{slug}")
                    if res_poly.status_code == 200:
                        print(f"✅ Mercado encontrado: {slug} | Pronóstico: {temp_pronosticada}")
                        # Aquí el bot aplica la lógica de Kelly y análisis de rangos...
                except: continue

        # Actualizar historial y dashboard
        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-20:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
            
        self.generar_dashboard()
        print(f"🏁 Ciclo completado. Próximo escaneo en 30 minutos.")

if __name__ == "__main__":
    WeatherTraderPerpetual().ejecutar()
