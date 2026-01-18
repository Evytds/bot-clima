import requests
import json
import re
import os
from datetime import datetime

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0  # Basado en tu capital disponible
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Costos Reales
FEES_POLYMARKET = 0.002    # 0.2%
GAS_POLYGON = 0.01        # USDC
SLIPPAGE = 0.01           # 1%
UMBRAL_VENTAJA = 12.0     # % de ventaja mínima para operar

class WeatherTraderPro:
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
            with open(ARCHIVO_BILLETERA, 'r') as f:
                return json.load(f)
        return {"balance": CAPITAL_INICIAL, "historial": [{"fecha": str(datetime.now().strftime("%H:%M")), "balance": CAPITAL_INICIAL}]}

    def _asegurar_archivos(self):
        """Crea los archivos básicos si no existen para evitar errores en GitHub Actions."""
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Mercado,Pronostico,Precio,Resultado\n")
        self.generar_dashboard()

    def calcular_kelly(self, prob_real, precio_mkt):
        p = prob_real / 100.0
        precio_real = (precio_mkt / 100.0) * (1 + SLIPPAGE + FEES_POLYMARKET)
        if precio_real <= 0 or precio_real >= 1: return 0
        b = (1 / precio_real) - 1
        q = 1 - p
        return max(0, (p * b - q) / b)

    def obtener_clima(self, lat, lon, unidad):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unidad}&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

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
                <div class="balance">${self.data["balance"]:.2f} USDC</div>
                <p>Interés Compuesto Activado</p>
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
        print(f"--- 📡 INICIANDO CICLO: {datetime.now()} ---")
        self._asegurar_archivos()
        
        # Simulación de ciclo para mercados del 18 de Enero
        for ciudad, info in self.ciudades.items():
            slug = f"highest-temperature-in-{ciudad}-on-january-18"
            try:
                res_poly = requests.get(f"https://gamma-api.polymarket.com/events/slug/{slug}")
                if res_poly.status_code != 200: continue
                
                temp_real = self.obtener_clima(info[0], info[1], info[2])
                for m in res_poly.json().get('markets', []):
                    # Lógica de detección de ventaja...
                    # Si detecta ventaja, se registra y actualiza balance
                    pass
            except: continue

        # Actualizar datos finales
        self.data["historial"].append({{"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]}})
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        self.generar_dashboard()
        print("✅ Ciclo completado y archivos actualizados.")

if __name__ == "__main__":
    WeatherTraderPro().ejecutar()
