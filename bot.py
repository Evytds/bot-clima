import requests
import json
import re
import os
import pandas as pd
from datetime import datetime, timedelta

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 # Basado en tu capital disponible
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Parámetros de Riesgo y Costos
RIESGO_MAX_OP = 0.15 # 15% del capital máximo por operación
UMBRAL_VENTAJA = 12.0 # 12% de ventaja mínima neta
FEES_TOTALES = 0.012 # 1.2% (incluye fee plataforma + slippage + gas estimado)

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
        hoy = datetime.now()
        manana = hoy + timedelta(days=1)
        return [hoy.strftime("%B-%d").lower(), manana.strftime("%B-%d").lower()]

    def obtener_clima(self, lat, lon, unidad):
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit={unidad}&timezone=auto&forecast_days=2"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max']
        except: return [None, None]

    def analizar_rendimiento_ciudades(self):
        if not os.path.exists(ARCHIVO_HISTORIAL): return ""
        try:
            df = pd.read_csv(ARCHIVO_HISTORIAL)
            if df.empty: return ""
            conteo = df['Ciudad'].value_counts().to_dict()
            filas = "".join([f"<tr><td>{c.upper()}</td><td>{v} ops</td></tr>" for c, v in conteo.items()])
            return filas
        except: return ""

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        tabla_ciudades = self.analizar_rendimiento_ciudades()
        
        # Color dinámico: verde si sube, rojo si baja
        color_tema = "#10b981"
        if len(valores) >= 2 and valores[-1] < valores[-2]:
            color_tema = "#ef4444"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Bot de Trading Perpetuo</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: sans-serif; background: #0f172a; color: white; text-align: center; margin: 0; }}
                .container {{ width: 90%; max-width: 800px; margin: auto; padding: 20px; }}
                .balance {{ font-size: 4em; color: {color_tema}; font-weight: bold; margin: 10px 0; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 15px; margin-top: 20px; }}
                table {{ width: 100%; margin-top: 10px; border-collapse: collapse; }}
                td {{ padding: 10px; border-top: 1px solid #334155; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p style="color: #94a3b8;">CAPITAL ACTUAL</p>
                <div class="balance">${self.data["balance"]:.2f}</div>
                <p style="color: #94a3b8;">USDC (Modo Simulación)</p>
                
                <div class="card"><canvas id="chart"></canvas></div>

                <div class="card">
                    <h3>🎯 Oportunidades por Ciudad</h3>
                    <table>{tabla_ciudades if tabla_ciudades else "<tr><td>Esperando datos...</td></tr>"}</table>
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
                            borderColor: '{color_tema}',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4
                        }}]
                    }},
                    options: {{ plugins: {{ legend: {{ display: false }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        print(f"--- 🔄 CICLO PERPETUO: {datetime.now()} ---")
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Mercado,Pronostico,Precio,Resultado\n")

        fechas = self.obtener_fechas_objetivo()
        for ciudad, coords in self.ciudades.items():
            temps = self.obtener_clima(coords[0], coords[1], coords[2])
            for i, f_str in enumerate(fechas):
                slug = f"highest-temperature-in-{ciudad}-on-{f_str}"
                temp_p = temps[i]
                if temp_p is not None:
                    # Aquí el bot procesa las señales y guarda en historial_ganancias.csv
                    # Por ahora imprimimos para confirmar el escaneo perpetuo
                    print(f"🔎 Escaneando: {slug} | Temp: {temp_p}")

        # Actualización de historial para gráfica
        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-20:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        self.generar_dashboard()
        print("✅ Ciclo completado.")

if __name__ == "__main__":
    WeatherTraderPerpetual().ejecutar()
