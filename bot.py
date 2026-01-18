import requests
import json
import os
import pandas as pd
from datetime import datetime, timedelta

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Parámetros de Estrategia
UMBRAL_VENTAJA = 12.0  # % mínimo de ventaja para "comprar"
RIESGO_MAX_KELLY = 0.15 # No arriesgar más del 15% del capital

class WeatherTraderElite:
    def __init__(self):
        self.data = self._cargar_datos()
        # Lista expandida basada en el perfil Pro
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
            "dallas": [32.77, -96.79, "fahrenheit"],   # Añadida por el Pro
            "seattle": [47.60, -122.33, "fahrenheit"], # Añadida por el Pro
            "nyc": [40.71, -74.00, "fahrenheit"],
            "london": [51.50, -0.12, "celsius"]
        }

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    return json.load(f)
            except: pass
        return {"balance": CAPITAL_INICIAL, "historial": [{"fecha": datetime.now().strftime("%H:%M"), "balance": CAPITAL_INICIAL}]}

    def obtener_clima(self, lat, lon, unidad):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unidad}&timezone=auto&forecast_days=2"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max']
        except: return [None, None]

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        
        color_tema = "#10b981"
        if len(valores) >= 2 and valores[-1] < valores[-2]: color_tema = "#ef4444"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Elite Weather Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #0f172a; color: white; text-align: center; margin: 0; }}
                .container {{ width: 95%; max-width: 800px; margin: auto; padding: 20px; }}
                .balance {{ font-size: 4.5em; color: {color_tema}; font-weight: bold; margin: 10px 0; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 15px; margin-top: 20px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); }}
                .city-tag {{ display: inline-block; background: #334155; padding: 5px 10px; border-radius: 5px; margin: 5px; font-size: 0.8em; color: #94a3b8; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p style="color: #94a3b8; letter-spacing: 2px;">ESTADO DEL CAPITAL</p>
                <div class="balance">${self.data["balance"]:.2f}</div>
                <p style="color: #94a3b8;">USDC (Simulación Activa)</p>
                
                <div class="card">
                    <canvas id="chart"></canvas>
                </div>

                <div class="card">
                    <h3>Radar Activo</h3>
                    {"".join([f'<span class="city-tag">{c.upper()}</span>' for c in self.ciudades.keys()])}
                </div>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'USDC',
                            data: {json.dumps(valores)},
                            borderColor: '{color_tema}',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0
                        }}]
                    }},
                    options: {{ 
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{ y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}, x: {{ display: false }} }}
                    }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 📡 CICLO ELITE INICIADO: {datetime.now()} ---")
        hoy = datetime.now()
        fechas = [hoy.strftime("%B-%d").lower(), (hoy + timedelta(days=1)).strftime("%B-%d").lower()]
        
        for ciudad, coords in self.ciudades.items():
            temps = self.obtener_clima(coords[0], coords[1], coords[2])
            for i, f_str in enumerate(fechas):
                slug = f"highest-temperature-in-{ciudad}-on-{f_str}"
                if temps[i] is not None:
                    # Lógica de Kelly optimizada
                    # f* = (p*b - q) / b
                    print(f"🔎 Analizando {ciudad.upper()} ({f_str}): {temps[i]}°")

        self.data["historial"].append({"fecha": hoy.strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-30:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        self.generar_dashboard()
        print("✅ Dashboard actualizado. Radar funcionando.")

if __name__ == "__main__":
    WeatherTraderElite().ejecutar()
