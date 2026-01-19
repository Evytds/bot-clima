import requests
import json
import os
import random
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN GLOBAL ===
CAPITAL_INICIAL = 50.0 
ARCHIVO_BILLETERA = "billetera_virtual.json"
ARCHIVO_HISTORIAL = "historial_ganancias.csv"
ARCHIVO_DASHBOARD = "index.html"

# Parámetros Cuantitativos Profesionales
EDGE_THRESHOLD = 0.05      # 5% de ventaja mínima
MAX_PCT_BY_TRADE = 0.02    # Máximo 2% por trade
COMISION_MERCADO = 0.02    # 2% de fee en ganancias
MIN_VOLUMEN_USD = 5000     # Filtro de liquidez mínima
STOP_LOSS_ABSOLUTO = 20.0  # Kill-switch

class WeatherTraderV3_2:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = ["Seoul", "Atlanta", "Dallas", "Seattle", "New York", "London"]
        self.poly_url = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"

    def _cargar_datos(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            try:
                with open(ARCHIVO_BILLETERA, 'r') as f:
                    d = json.load(f)
                    if "peak_balance" not in d: d["peak_balance"] = d["balance"]
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
        """Consulta Polymarket con filtro de liquidez absoluta"""
        try:
            query = """
            {
              markets(first: 5, where: {question_contains: "%s", category: "Weather"}) {
                question
                outcomes { name, price }
                volume
              }
            }
            """ % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            markets = res["data"]["markets"]
            
            # Filtro de volumen y existencia
            valid_markets = [m for m in markets if float(m["volume"]) >= MIN_VOLUMEN_USD]
            if not valid_markets: return None

            # Seleccionamos el más líquido
            market = max(valid_markets, key=lambda m: float(m["volume"]))
            yes_price = next(float(o["price"]) for o in market["outcomes"] if o["name"] == "Yes")
            return yes_price
        except: return None

    def calcular_prob_granular(self, temp):
        """Modelo de probabilidad mejorado (Heurística de 4 niveles)"""
        if temp > 38 or temp < -5: return 0.80
        elif temp > 32 or temp < 5: return 0.70
        elif temp > 28 or temp < 12: return 0.60
        else: return 0.52

    def calcular_ev_neto(self, prob, precio, stake):
        p_ganar = prob
        p_perder = 1 - prob
        ganancia_neta = ((stake / precio) - stake) * (1 - COMISION_MERCADO)
        return (p_ganar * ganancia_neta) - (p_perder * stake)

    def ejecutar_trade(self, ciudad):
        precio_yes = self.obtener_precio_polymarket(ciudad)
        temp = self.obtener_clima(ciudad)
        
        if precio_yes is None or temp is None: return

        prob_modelo_yes = self.calcular_prob_granular(temp)
        
        # DETERMINACIÓN DE LADO (Lógica Simétrica)
        # Si nuestra prob es mayor al precio, operamos YES. Si es menor, operamos NO.
        if prob_modelo_yes > precio_yes:
            lado, prob, precio = "YES", prob_modelo_yes, precio_yes
        else:
            lado, prob, precio = "NO", (1 - prob_modelo_yes), (1 - precio_yes)

        edge = prob - precio
        
        if edge > EDGE_THRESHOLD:
            # Position Sizing: 2% Cap
            stake = self.data["balance"] * min(edge, MAX_PCT_BY_TRADE)
            if stake < 1.0: return

            ev = self.calcular_ev_neto(prob, precio, stake)
            if ev <= 0: return

            # SIMULACIÓN CON RUIDO (Forecast Error)
            # Añadimos un error gaussiano de 5% a la probabilidad real
            prob_simulada = max(0.01, min(0.99, random.gauss(prob, 0.05)))
            
            if random.random() < prob_simulada:
                resultado_dinero = ((stake / precio) - stake) * (1 - COMISION_MERCADO)
                res_str = "WIN"
            else:
                resultado_dinero = -stake
                res_str = "LOSS"

            # Actualización de Balance y Peak
            self.data["balance"] += resultado_dinero
            if self.data["balance"] > self.data["peak_balance"]:
                self.data["peak_balance"] = self.data["balance"]

            print(f"📊 {ciudad} ({lado}) | Edge: {edge:.2%} | EV: ${ev:.2f} | {res_str}: ${resultado_dinero:.2f}")
            
            with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()},{ciudad},{lado},{prob:.2f},{precio:.2f},{edge:.2f},{stake:.2f},{ev:.2f},{resultado_dinero:.2f}\n")

    def ejecutar(self):
        if self.data["balance"] < STOP_LOSS_ABSOLUTO: return

        # Barajamos ciudades para evitar sesgo de ejecución
        ciudades_shuffled = self.ciudades.copy()
        random.shuffle(ciudades_shuffled)

        for ciudad in ciudades_shuffled:
            self.ejecutar_trade(ciudad)

        # Cálculo de Drawdown
        dd = (self.data["peak_balance"] - self.data["balance"]) / self.data["peak_balance"]
        
        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-50:]
        with open(ARCHIVO_BILLETERA, 'w') as f: json.dump(self.data, f)
        
        print(f"✅ Balance: ${self.data['balance']:.2f} | Peak: ${self.data['peak_balance']:.2f} | DD: {dd:.2%}")

if __name__ == "__main__":
    WeatherTraderV3_2().ejecutar()
