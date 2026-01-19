import requests
import json
import os
import random
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN QUANT ===
CAPITAL_INICIAL = 50.0 
PROFIT_PROTECTION_LIMIT = 150.0 # No operar si el balance cae de aquí (Protección de ganancias)
STOP_LOSS_ABSOLUTO = 25.0       # Kill-switch de seguridad total
EDGE_THRESHOLD = 0.05           # 5% de ventaja mínima
MAX_PCT_BY_TRADE = 0.02         # 2% cap por operación
COMISION_MERCADO = 0.02         # 2% fee
MIN_VOLUMEN_USD = 5000          # Filtro de liquidez

ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

class WeatherTraderV3_3:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = ["Seoul", "Atlanta", "Dallas", "Seattle", "New York", "London"]
        self.poly_url = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    d = json.load(f)
                    d.setdefault("peak_balance", d["balance"])
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

    def obtener_precio_polymarket(self, ciudad):
        try:
            query = '{ markets(first: 5, where: {question_contains: "%s", category: "Weather"}) { outcomes { name, price } volume } }' % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            markets = [m for m in res["data"]["markets"] if float(m["volume"]) >= MIN_VOLUMEN_USD]
            if not markets: return None
            market = max(markets, key=lambda m: float(m["volume"]))
            return next(float(o["price"]) for o in market["outcomes"] if o["name"] == "Yes")
        except: return None

    def calcular_prob_granular(self, temp):
        if temp > 38 or temp < -5: return 0.78
        elif temp > 32 or temp < 5: return 0.68
        else: return 0.53

    def calcular_ev_neto(self, prob, precio, stake):
        # Esperanza Matemática: $E = (P \cdot W_{n}) - (Q \cdot L)$
        ganancia_neta = ((stake / precio) - stake) * (1 - COMISION_MERCADO)
        return (prob * ganancia_neta) - ((1 - prob) * stake)

    def calcular_metricas(self):
        if not os.path.exists(ARCHIVO_HISTORIAL): return None
        try:
            df = pd.read_csv(ARCHIVO_HISTORIAL)
            if len(df) < 5: return None
            win_rate = (df.iloc[:, -1] > 0).mean() * 100
            ganancias = df[df.iloc[:, -1] > 0].iloc[:, -1].sum()
            perdidas = abs(df[df.iloc[:, -1] < 0].iloc[:, -1].sum())
            pf = ganancias / perdidas if perdidas > 0 else 0
            expectancy = df.iloc[:, -1].sum() / len(df)
            return {"wr": round(win_rate, 1), "pf": round(pf, 2), "ev": round(expectancy, 2), "total": len(df)}
        except: return None

    def ejecutar_trade(self, ciudad):
        precio_yes = self.obtener_precio_polymarket(ciudad)
        temp = self.obtener_clima(ciudad)
        if precio_yes is None or temp is None: return

        prob_yes = self.calcular_prob_granular(temp)
        # Lógica de Lado (Simetría)
        if prob_yes > precio_yes: lado, prob, precio = "YES", prob_yes, precio_yes
        else: lado, prob, precio = "NO", (1 - prob_yes), (1 - precio_yes)

        edge = prob - precio
        if edge > EDGE_THRESHOLD:
            stake = self.data["balance"] * min(edge, MAX_PCT_BY_TRADE)
            if stake < 1.0: return
            ev = self.calcular_ev_neto(prob, precio, stake)
            if ev <= 0: return

            # Simulación con error de pronóstico (Ruido Gaussiano)
            prob_sim = max(0.01, min(0.99, random.gauss(prob, 0.05)))
            if random.random() < prob_sim:
                res_dinero = ((stake / precio) - stake) * (1 - COMISION_MERCADO)
                tipo = "WIN"
            else:
                res_dinero = -stake
                tipo = "LOSS"

            self.data["balance"] += res_dinero
            if self.data["balance"] > self.data["peak_balance"]: self.data["peak_balance"] = self.data["balance"]
            
            with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()},{ciudad},{lado},{prob:.2f},{precio:.2f},{edge:.2f},{stake:.2f},{ev:.2f},{res_dinero:.2f}\n")

    def generar_dashboard(self):
        m = self.calcular_metricas()
        labels = [h["fecha"] for h in self.data["historial"]]
        valores = [h["balance"] for h in self.data["historial"]]
        color = "#10b981" if self.data["balance"] >= CAPITAL_INICIAL else "#ef4444"
        
        stats_html = f"""
            <div class="stats-grid">
                <div class="stat-card"><h3>Win Rate</h3><p>{m['wr'] if m else '--'}%</p></div>
                <div class="stat-card"><h3>Profit Factor</h3><p>{m['pf'] if m else '--'}</p></div>
                <div class="stat-card"><h3>Expectancy</h3><p>${m['ev'] if m else '--'}</p></div>
            </div>
        """ if m else ""

        html = f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ background: #0f172a; color: white; font-family: sans-serif; margin: 0; padding: 20px; text-align: center; }}
                .balance {{ font-size: 3.5em; color: {color}; font-weight: bold; margin: 20px 0; }}
                .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; max-width: 600px; margin: 20px auto; }}
                .stat-card {{ background: #1e293b; padding: 10px; border-radius: 10px; }}
                .stat-card h3 {{ font-size: 0.7em; color: #94a3b8; margin: 0; }}
                .stat-card p {{ font-size: 1.2em; margin: 5px 0 0 0; }}
                .container {{ max-width: 800px; margin: auto; }}
                canvas {{ background: #1e293b; padding: 15px; border-radius: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <p style="color: #94a3b8; letter-spacing: 2px;">WEATHERTRADER QUANT V3.3</p>
                <div class="balance">${self.data['balance']:.2f}</div>
                {stats_html}
                <canvas id="chart"></canvas>
                <p style="color: #64748b; font-size: 0.8em; margin-top: 20px;">Protect Limit: ${PROFIT_PROTECTION_LIMIT} | Trades: {m['total'] if m else 0}</p>
            </div>
            <script>
                new Chart(document.getElementById('chart'), {{
                    type: 'line',
                    data: {{ labels: {json.dumps(labels)}, 
                    datasets: [{{ data: {json.dumps(valores)}, borderColor: '{color}', borderWidth: 3, tension: 0.4, pointRadius: 0, fill: false }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }} }}
                }});
            </script>
        </body>
        </html>"""
        with open(ARCHIVO_DASHBOARD, 'w', encoding='utf-8') as f: f.write(html)

    def ejecutar(self):
        # PROTECCIÓN DE GANANCIAS:
        if self.data["balance"] < PROFIT_PROTECTION_LIMIT:
            print(f"🛑 PROTECCIÓN ACTIVADA: Balance (${self.data['balance']}) inferior al límite de seguridad.")
            return
        
        if not os.path.exists(ARCHIVO_HISTORIAL):
            with open(ARCHIVO_HISTORIAL, 'w', encoding='utf-8') as f:
                f.write("Fecha,Ciudad,Lado,Prob,Precio,Edge,Stake,EV,Resultado\n")

        ciudades_shuffled = self.ciudades.copy()
        random.shuffle(ciudades_shuffled)
        for c in ciudades_shuffled: self.ejecutar_trade(c)

        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]
        with open(ARCHIVO_BILLETERA, 'w') as f: json.dump(self.data, f)
        self.generar_dashboard()

if __name__ == "__main__":
    WeatherTraderV3_3().ejecutar()
