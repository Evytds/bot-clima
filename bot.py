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
            "nyc": [40.71, -74.00, "fahrenheit"]
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
        
        # Lógica de color según tendencia
        color_balance = "#10b981" # Verde por defecto
        if len(valores) >= 2:
            if valores[-1] < valores[-2]:
                color_balance = "#ef4444" # Rojo si bajó
        
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
                .label {{ color: #94a3b8; font-size: 1.2em; text-transform: uppercase; letter-spacing: 1px; }}
                .chart-box {{ background: #1e293b; padding: 20px; border-radius: 15px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="label">Capital Total</div>
                <div class="balance">${self.data["balance"]:.2f}</div>
                <div class="label">USDC</div>
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
        print(f"--- 🚀 CICLO USDC ACTIVO: {datetime.now()} ---")
        
        # Aseguramos existencia de historial
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Mercado,Pronostico,Precio,Resultado\n")

        # Registro de punto actual
        self.data["historial"].append({
            "fecha": datetime.now().strftime("%H:%M"), 
            "balance": self.data["balance"]
        })
        
        # Mantener historial manejable
        self.data["historial"] = self.data["historial"][-20:]

        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        
        self.generar_dashboard()
        print(f"✅ Dashboard actualizado. Balance actual: ${self.data['balance']} USDC")

if __name__ == "__main__":
    WeatherTraderPro().ejecutar()
