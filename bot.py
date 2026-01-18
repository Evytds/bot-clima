import requests
import json
import re
import os
from datetime import datetime

# === PARÁMETROS ===
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_DASHBOARD = "index.html"
MODO_SIMULACION = True

class SistemaMaestroConDashboard:
    def __init__(self):
        self.datos = self.cargar_datos()
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
            "nyc": [40.71, -74.00, "fahrenheit"]
        }

    def cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            with open(ARCHIVO_BILLETERA, 'r') as f:
                return json.load(f)
        return {"balance": 50.0, "historial": [{"fecha": str(datetime.now().date()), "balance": 50.0}]}

    def guardar_datos(self, balance_actual):
        self.datos["balance"] = balance_actual
        self.datos["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": round(balance_actual, 2)})
        # Mantener solo los últimos 20 registros para la gráfica
        self.datos["historial"] = self.datos["historial"][-20:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.datos, f)
        self.generar_html()

    def generar_html(self):
        labels = [h["fecha"] for h in self.datos["historial"]]
        valores = [h["balance"] for h in self.datos["historial"]]
        
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Bot Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #121212; color: white; text-align: center; }}
                .container {{ width: 90%; max-width: 600px; margin: auto; padding-top: 20px; }}
                .balance {{ font-size: 2.5em; color: #00ff88; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Balance del Bot</h2>
                <div class="balance">${self.datos["balance"]:.2f} USDC</div>
                <canvas id="grafica"></canvas>
            </div>
            <script>
                new Chart(document.getElementById('grafica'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(labels)},
                        datasets: [{{
                            label: 'Capital USDC',
                            data: {json.dumps(valores)},
                            borderColor: '#00ff88',
                            tension: 0.3,
                            fill: true,
                            backgroundColor: 'rgba(0, 255, 136, 0.1)'
                        }}]
                    }},
                    options: {{ scales: {{ y: {{ grid: {{ color: '#333' }} }} }} }}
                }});
            </script>
        </body>
        </html>
        """
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html_template)

    def ejecutar(self):
        print(f"--- 📡 ESCANEANDO OPORTUNIDADES... BALANCE: ${self.datos['balance']} ---")
        # Aquí va tu lógica de escaneo anterior...
        # Simulamos una ganancia para probar el dashboard
        nuevo_balance = self.datos["balance"] + 0.50 
        self.guardar_datos(nuevo_balance)
        print("✅ Dashboard actualizado.")

if __name__ == "__main__":
    bot = SistemaMaestroConDashboard()
    bot.ejecutar()
