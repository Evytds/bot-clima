import requests
import json
import re
import os
from datetime import datetime

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 # Basado en tu capital de 50 USDC
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
                .balance {{ font-size: 3em; color: #10b981; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Balance del Bot</h1>
                <div class="balance">${{self.data["balance"]:.2f}} USDC</div>
                <canvas id="chart"></canvas>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'Capital (USDC)',
                            data: {json.dumps(valores)},
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4
                        }}]
                    }},
                    options: {{ scales: {{ y: {{ grid: {{ color: '#1e293b' }} }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 🚀 INICIANDO CICLO: {datetime.now()} ---")
        
        # Aseguramos que el historial.csv exista
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Mercado,Pronostico,Precio,Resultado\n")

        # Registro del punto actual en el historial (CORREGIDO: Una sola llave)
        self.data["historial"].append({
            "fecha": datetime.now().strftime("%H:%M"), 
            "balance": self.data["balance"]
        })
        
        # Mantener solo los últimos 20 puntos para la gráfica
        self.data["historial"] = self.data["historial"][-20:]

        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        
        self.generar_dashboard()
        print("✅ Ciclo completado sin errores.")

if __name__ == "__main__":
    WeatherTraderPro().ejecutar()
