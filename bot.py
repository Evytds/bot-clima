import requests
import json
import re
import os
from datetime import datetime

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

class WeatherTraderPro:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
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

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        
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
                .balance {{ font-size: 4em; color: #10b981; font-weight: bold; margin: 20px 0; }}
                .chart-box {{ background: #1e293b; padding: 20px; border-radius: 15px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Capital en USDC</h1>
                <div class="balance">${self.data["balance"]:.2f}</div>
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
                            label: 'Balance USDC',
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
                        plugins: {{ legend: {{ labels: {{ color: 'white' }} }} }}
                    }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 🚀 INICIANDO CICLO: {datetime.now()} ---")
        
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Mercado,Pronostico,Precio,Resultado\n")

        self.data["historial"].append({
            "fecha": datetime.now().strftime("%H:%M"), 
            "balance": self.data["balance"]
        })
        
        self.data["historial"] = self.data["historial"][-20:]

        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        
        self.generar_dashboard()
        print("✅ Ciclo completado sin conversiones de moneda.")

if __name__ == "__main__":
    WeatherTraderPro().ejecutar()
