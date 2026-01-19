import requests
import json
import os
import random
import re
import math
import pandas as pd
from datetime import datetime

# === CONFIGURACIÓN CIENTÍFICA v3.6 ===
CAPITAL_INICIAL = 196.70
BASE_SIGMA = 1.2          # Error base en °C
EDGE_THRESHOLD = 0.07     # Umbral de ventaja (subido por seguridad)
MAX_EVENT_EXPOSURE = 0.02 # Reducido a 2% por trade individual
MAX_CYCLE_EXPOSURE = 0.05 # Límite de riesgo total por ejecución (5%)
COMISION_GANANCIA = 0.02

class WeatherTraderV3_6:
    def __init__(self):
        self.data = self._cargar_datos()
        self.ciudades_config = {
            "Seoul": {"lat": 37.56, "lon": 126.97},
            "Atlanta": {"lat": 33.74, "lon": -84.38},
            "Dallas": {"lat": 32.77, "lon": -96.79},
            "Seattle": {"lat": 47.60, "lon": -122.33},
            "New York": {"lat": 40.71, "lon": -74.00},
            "London": {"lat": 51.50, "lon": -0.12}
        }
        self.poly_url = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"
        self.current_cycle_stake = 0 # Tracking de exposición cruzada

    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            with open("billetera_virtual.json", 'r') as f: return json.load(f)
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def obtener_clima(self, lat, lon):
        try:
            # Consultamos pronóstico a 24h para mayor precisión
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            res = requests.get(url).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def parsear_mercado(self, pregunta):
        # FILTRO DE RELEVANCIA: Solo mercados térmicos
        if not any(k in pregunta.lower() for k in ["temp", "temperature", "degrees", "celsius", "fahrenheit"]):
            return None, None
            
        try:
            numeros = re.findall(r"[-+]?\d*\.\d+|\d+", pregunta)
            if not numeros: return None, None
            threshold = float(numeros[0])
            op = "<" if any(w in pregunta.lower() for w in ["below", "under", "less", "lower"]) else ">"
            return threshold, op
        except: return None, None

    def calcular_prob_cientifica(self, forecast, umbral, operador):
        # Sigma con penalización leve por incertidumbre base
        sigma = BASE_SIGMA * 1.1 
        z = (umbral - forecast) / (sigma * math.sqrt(2))
        phi = 0.5 * (1 + math.erf(z))
        return (1 - phi) if operador == ">" else phi

    def ejecutar_trade(self, ciudad, config):
        # Control de exposición del ciclo
        if self.current_cycle_stake >= (self.data["balance"] * MAX_CYCLE_EXPOSURE):
            return

        mercados = self.obtener_precios_polymarket(ciudad)
        t_forecast = self.obtener_clima(config["lat"], config["lon"])
        if not mercados or t_forecast is None: return

        for mkt in mercados:
            pregunta = mkt["question"]
            umbral, op = self.parsear_mercado(pregunta)
            if umbral is None: continue

            p_yes_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "yes")
            p_no_mkt = next(float(o["price"]) for o in mkt["outcomes"] if o["name"].lower() == "no")

            prob_yes_mod = self.calcular_prob_cientifica(t_forecast, umbral, op)
            prob_no_mod = 1 - prob_yes_mod

            # Lógica de Edge
            edge_yes = prob_yes_mod - p_yes_mkt
            edge_no = prob_no_mod - p_no_mkt

            if edge_yes > EDGE_THRESHOLD:
                self.procesar(ciudad, "YES", prob_yes_mod, p_yes_mkt, edge_yes, pregunta)
            elif edge_no > EDGE_THRESHOLD:
                self.procesar(ciudad, "NO", prob_no_mod, p_no_mkt, edge_no, pregunta)

    def procesar(self, ciudad, lado, prob, precio, edge, pregunta):
        stake = self.data["balance"] * min(edge * 0.4, MAX_EVENT_EXPOSURE)
        
        # Verificar si este trade excede el cluster cap
        if self.current_cycle_stake + stake > (self.data["balance"] * MAX_CYCLE_EXPOSURE):
            stake = (self.data["balance"] * MAX_CYCLE_EXPOSURE) - self.current_cycle_stake
        
        if stake < 1.0: return

        win_neto = (stake * (1/precio - 1)) * (1 - COMISION_GANANCIA)
        ev_neto = (prob * win_neto) - ((1 - prob) * stake)

        if ev_neto > 0:
            self.current_cycle_stake += stake
            outcome_real = 1 if random.random() < prob else 0 # Simulación para validación
            res_dinero = win_neto if outcome_real == 1 else -stake
            
            # BRIER SCORE COMPONENT: (Probabilidad - Resultado Real)^2
            brier_component = (prob - outcome_real) ** 2

            self.data["balance"] += res_dinero
            
            # Log extendido para validación científica
            with open("historial_ganancias.csv", 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now()},{ciudad},{lado},{prob:.4f},{precio:.2f},{stake:.2f},{ev_neto:.2f},{res_dinero:.2f},{brier_component:.4f}\n")

    def obtener_precios_polymarket(self, ciudad):
        try:
            query = '{ markets(first: 3, where: {question_contains_nocase: "%s"}) { question outcomes { name price } volume } }' % ciudad
            res = requests.post(self.poly_url, json={"query": query}).json()
            return [m for m in res["data"]["markets"] if float(m["volume"]) >= 5000]
        except: return []

    def ejecutar(self):
        if not os.path.exists("historial_ganancias.csv"):
            with open("historial_ganancias.csv", 'w') as f:
                f.write("Fecha,Ciudad,Lado,Prob,Precio,Stake,EV,Resultado,Brier_Comp\n")

        for ciudad, config in self.ciudades_config.items():
            self.ejecutar_trade(ciudad, config)
            
        with open("billetera_virtual.json", 'w') as f: json.dump(self.data, f)

if __name__ == "__main__":
    WeatherTraderV3_6().ejecutar()
