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

# Parámetros Cuantitativos
EDGE_THRESHOLD = 0.05      
MAX_PCT_BY_TRADE = 0.02    
COMISION_MERCADO = 0.02    
STOP_LOSS_ABSOLUTO = 20.0  # Si bajamos de $20, el bot muere.

class WeatherTraderV3_1:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades = ["Seoul", "Atlanta", "Dallas", "Seattle", "New York", "London"]
        # URL del Subgraph de Polymarket
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
        # Simplificamos coordenadas para el ejemplo (Se podrían mapear en un dict)
        coords = {"Seoul": (37.56, 126.97), "Atlanta": (33.74, -84.38), "Dallas": (32.77, -96.79)}
        lat, lon = coords.get(ciudad, (40.71, -74.00))
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def obtener_precio_polymarket(self, ciudad):
        """Consulta real al Subgraph de Polymarket"""
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
            if not markets: return None

            # Seleccionamos el mercado con más volumen para asegurar liquidez
            market = max(markets, key=lambda m: float(m["volume"]))
            yes_price = next(float(o["price"]) for o in market["outcomes"] if o["name"] == "Yes")
            return yes_price
        except: return None

    def calcular_ev_corregido(self, prob_real, precio_mercado, stake):
        """
        Cálculo de EV Neto: E = (P * Ganancia_Neta) - (Q * Stake)
        Ganancia_Neta = ((Stake / Precio) - Stake) * (1 - Comisión)
        """
        p_ganar = prob_real
        p_perder = 1 - prob_real
        
        ganancia_bruta = (stake / precio_mercado) - stake
        ganancia_neta = ganancia_bruta * (1 - COMISION_MERCADO)
        
        ev = (p_ganar * ganancia_neta) - (p_perder * stake)
        return ev

    def ejecutar_trade(self, ciudad):
        precio_mkt = self.obtener_precio_polymarket(ciudad)
        temp = self.obtener_clima(ciudad)
        
        if precio_mkt is None or temp is None: return

        # Modelo Heurístico (Certeza basada en extremos)
        prob_modelo = 0.75 if (temp > 32 or temp < 5) else 0.55
        
        edge = prob_modelo - precio_mkt
        
        if abs(edge) > EDGE_THRESHOLD:
            lado = "YES" if edge > 0 else "NO"
            prob_final = prob_modelo if lado == "YES" else (1 - prob_modelo)
            
            # Position Sizing
            stake = self.data["balance"] * min(abs(edge), MAX_PCT_BY_TRADE)
            
            if stake < 1.0: return

            ev_neto = self.calcular_ev_corregido(prob_final, precio_mkt, stake)
            
            # Solo ejecutamos si el EV neto sigue siendo positivo tras comisiones
            if ev_neto <= 0: return

            # Simulación Monte Carlo (Paper Trading)
            if random.random() < prob_final:
                resultado_dinero = ((stake / precio_mkt) - stake) * (1 - COMISION_MERCADO)
                tipo = "WIN"
            else:
                resultado_dinero = -stake
                tipo = "LOSS"

            self.data["balance"] += resultado_dinero
            # Actualizar Peak para Drawdown
            if self.data["balance"] > self.data["peak_balance"]:
                self.data["peak_balance"] = self.data["balance"]

            print(f"📡 {ciudad} ({lado}) | Edge: {edge:.2%} | EV Neto: ${ev_neto:.2f} | {tipo}: ${resultado_dinero:.2f}")
            
            with open(ARCHIVO_HISTORIAL, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()},{ciudad},{prob_final:.2f},{precio_mkt:.2f},{ev_neto:.2f},{resultado_dinero:.2f}\n")

    def ejecutar(self):
        if self.data["balance"] < STOP_LOSS_ABSOLUTO:
            print("🛑 Kill-switch activado. Saldo insuficiente.")
            return

        for ciudad in self.ciudades:
            self.ejecutar_trade(ciudad)

        # Drawdown actual
        dd = (self.data["peak_balance"] - self.data["balance"]) / self.data["peak_balance"]
        
        self.data["historial"].append({"fecha": datetime.now().strftime("%H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-50:]
        with open(ARCHIVO_BILLETERA, 'w') as f: json.dump(self.data, f)
        print(f"✅ Ciclo Terminado. Balance: ${self.data['balance']:.2f} | Max DD: {dd:.2%}")

if __name__ == "__main__":
    WeatherTraderV3_1().ejecutar()
