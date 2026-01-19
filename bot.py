import requests
import json
import os
import random
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN QUANT v3.4 ===
CAPITAL_INICIAL = 50.0 
STOP_LOSS_ABSOLUTO = 25.0       # Detener si el capital cae a $25
TAKE_PROFIT_GOAL = 500.0        # Meta de retiro (Take Profit)
EDGE_THRESHOLD = 0.05           # 5% de ventaja mínima para operar
MAX_PCT_BY_TRADE = 0.02         # Máximo 2% del capital por operación
COMISION_GANANCIA = 0.02        # 2% fee solo sobre el beneficio neto
MIN_VOLUMEN_USD = 5000          # Filtro de liquidez mínima

ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

class WeatherTraderV3_4:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = ["Seoul", "Atlanta", "Dallas", "Seattle", "New York", "London"]
        self.poly_url = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    d = json.load(f)
                    # Asegurar que existan las llaves de persistencia
                    if "peak_balance" not in d: d["peak_balance"] = d["balance"]
                    if "historial" not in d: d["historial"] = []
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def obtener_clima(self, ciudad):
        coords = {"Seoul": (37.56, 126.97), "Atlanta": (33.74, -84.38), "Dallas": (32.77, -96.79), 
                  "Seattle": (47.60, -122.33), "New York": (40.71, -74.00), "London": (51.50, -0.12)}
        lat, lon = coords.get(ciudad, (40.71, -74.00))
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def obtener_precios_polymarket(self, ciudad):
        """Consulta precios de YES y NO reales con filtro de volumen"""
        try:
            query = '{ markets(first: 5, where: {question_contains_nocase: "%s"}) { outcomes { name, price } volume } }' % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            markets = [m for m in res["data"]["markets"] if float(m["volume"]) >= MIN_VOLUMEN_USD]
            if not markets: return None
            
            # Seleccionar el mercado más líquido
            m = max(markets, key=lambda x: float(x["volume"]))
            p_yes = next(float(o["price"]) for o in m["outcomes"] if o["name"].lower() == "yes")
            p_no = next(float(o["price"]) for o in m["outcomes"] if o["name"].lower() == "no")
            return p_yes, p_no
        except: return None

    def calcular_prob_suave(self, temp):
        """Modelo de probabilidad suavizado para evitar sesgos extremos"""
        if temp > 35 or temp < 0: return 0.65
        elif temp > 30 or temp < 10: return 0.58
        else: return 0.52

    def ejecutar_trade(self, ciudad):
        precios = self.obtener_precios_polymarket(ciudad)
        temp = self.obtener_clima(ciudad)
        if precios is None or temp is None: return

        p_yes_mkt, p_no_mkt = precios
        prob_yes_mod = self.calcular_prob_suave(temp)
        prob_no_mod = 1 - prob_yes_mod

        # Lógica de Selección de Lado (Mejor Edge)
        edge_yes = prob_yes_mod - p_yes_mkt
        edge_no = prob_no_mod - p_no_mkt

        if edge_yes > edge_no and edge_yes > EDGE_THRESHOLD:
            lado, prob, precio = "YES", prob_yes_mod, p_yes_mkt
            edge = edge_yes
        elif edge_no > edge_yes and edge_no > EDGE_THRESHOLD:
            lado, prob, precio = "NO", prob_no_mod, p_no_mkt
            edge = edge_no
        else: return

        # Tamaño de la posición (Stake) con reducción de volatilidad
        stake = self.data["balance"] * min(edge * 0.5, MAX_PCT_BY_TRADE)
        if stake < 1.0: return

        # Matemática de EV Real (Binaria + Fees en Ganancia)
        win_bruto = stake * (1/precio - 1)
        win_neto = win_bruto * (1 - COMISION_GANANCIA)
        ev_neto = (prob * win_neto) - ((1 - prob) * stake)
        
        if ev_neto <= 0: return

        # Simulación Monte Carlo con Error de Pronóstico
        prob_sim = max(0.01, min(0.99, random.gauss(prob, 0.05)))
        
        if random.random() < prob_sim:
            res_dinero = win_neto
            res_str = "WIN"
        else:
            res_dinero = -stake
            res_str = "LOSS"

        self.data["balance"] += res_dinero
        if self.data["balance"] > self.data["peak_balance"]:
            self.data["peak_balance"] = self.data["balance"]

        print(f"📊 {ciudad} ({lado}) | Edge: {edge:.2%} | EV: ${ev_neto:.2f} | {res_str}: ${res_dinero:.2f}")
        
        with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now()},{ciudad},{lado},{prob:.2f},{precio:.2f},{stake:.2f},{ev_neto:.2f},{res_dinero:.2f}\n")

    def generar_dashboard(self):
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        color = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"
        dd = (self.data["peak_balance"] - self.data["balance"]) / self.data["peak_balance"] * 100

        html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ background: #0f172a; color: white; font-family: sans-serif; text-align: center; padding: 20px; }}
                .balance {{ font-size: 3.5em; color: {color}; font-weight: bold; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 15px; max-width: 700px; margin: 20px auto; }}
                .stat {{ color: #94a3b8; font-size: 0.8em; margin: 5px; }}
            </style>
        </head>
        <body>
            <p>WEATHERTRADER QUANT V3.4</p>
            <div class="balance">${self.data['balance']:.2f}</div>
            <div class="card">
                <canvas id="c"></canvas>
            </div>
            <div class="stat">Max Drawdown: {dd:.2f}% | Peak: ${self.data['peak_balance']:.2f}</div>
            <script>
                new Chart(document.getElementById('c'), {{
                    type: 'line',
                    data: {{ labels: {json.dumps(labels)}, 
                    datasets: [{{ data: {json.dumps(valores)}, borderColor: '{color}', tension: 0.4, pointRadius: 0, fill: false }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f:
            f.write(html)

    def ejecutar(self):
        # SEGURIDAD: Kill Switch
        if self.data["balance"] <= STOP_LOSS_ABSOLUTO:
            print("☠️ SISTEMA DETENIDO: Capital por debajo del mínimo de seguridad.")
            return
        
        if self.data["balance"] >= TAKE_PROFIT_GOAL:
            print("💰 META ALCANZADA: Retirando beneficios.")
            return

        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Lado,Prob,Precio,Stake,EV,Resultado\n")

        ciudades_shuffled = self.ciudades.copy()
        random.shuffle(ciudades_shuffled)
        for c in ciudades_shuffled:
            self.ejecutar_trade(c)

        # Guardar historial para el gráfico (Persistencia)
        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]
        
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump(self.data, f)
        
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderV3_4().ejecutar()
