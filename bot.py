import requests
import json
import re
import os
import math
from datetime import datetime

# === CONFIGURACIÓN DE RIESGO ===
CAPITAL_TOTAL = 50.0  # Tus 50 USDC
RIESGO_MAX_POR_OPERACION = 0.10  # No invertir más del 10% del capital total en un solo rango
UMBRAL_VENTAJA_MINIMA = 15.0  # Solo operar si hay una ventaja del 15% o más
MODO_SIMULACION = True # Cambiar a False cuando conectes tus API Keys reales

class CryptoWeatherBot:
    def __init__(self):
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
            "nyc": [40.71, -74.00, "fahrenheit"],
            "london": [51.50, -0.12, "celsius"],
            "toronto": [43.65, -79.38, "celsius"]
        }

    def calcular_kelly(self, prob_real, precio_mercado):
        """
        Calcula el tamaño de la posición usando el Criterio de Kelly.
        p = probabilidad (0-1), b = beneficio (odds)
        """
        p = prob_real / 100.0
        precio = precio_mercado / 100.0
        if precio <= 0 or precio >= 1: return 0
        
        b = (1 / precio) - 1 # Ganancia neta recibida por cada $1 apostado
        q = 1 - p
        
        f_star = (p * b - q) / b # Fracción de Kelly
        return max(0, f_star) # No apostar si es negativo

    def obtener_clima(self, lat, lon, unidad):
        try:
            res = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_max", 
                        "temperature_unit": unidad, "timezone": "auto", "forecast_days": 1}
            ).json()
            return res['daily']['temperature_2m_max'][0]
        except:
            return None

    def escanear_y_operar(self):
        print(f"--- 🚀 EJECUTANDO SISTEMA MAESTRO: {datetime.now()} ---")
        
        # 1. BUSCAR MERCADOS ACTIVOS
        objetivos = [f"highest-temperature-in-{c}-on-january-18" for c in self.ciudades.keys()]
        
        for slug in objetivos:
            try:
                url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
                r = requests.get(url)
                if r.status_code != 200: continue
                
                ev = r.json()
                ciudad_key = slug.split('-')[3]
                lat, lon, unidad = self.ciudades[ciudad_key]
                
                # 2. ANÁLISIS CIENTÍFICO
                temp_real = self.obtener_clima(lat, lon, unidad)
                if temp_real is None: continue

                # 3. EVALUAR CADA RANGO (MARKET)
                for m in ev.get('markets', []):
                    nombre_rango = m.get('groupItemTitle', 'Rango')
                    precios = json.loads(m.get('outcomePrices', '["0", "0"]'))
                    precio_yes = float(precios[0]) * 100
                    
                    # Determinar si el pronóstico cae en este rango
                    nums = [int(n) for n in re.findall(r'\d+', nombre_rango)]
                    es_probable = False
                    if len(nums) >= 2: es_probable = nums[0] <= temp_real <= nums[1]
                    elif len(nums) == 1: es_probable = round(temp_real) == nums[0]

                    # 4. GESTIÓN DE RIESGO Y OPORTUNIDAD
                    if es_probable:
                        ventaja = (80 if es_probable else 0) - precio_yes # Asumimos 80% de confianza del satélite
                        
                        if ventaja >= UMBRAL_VENTAJA_MINIMA:
                            # Cálculo de Kelly
                            fraccion_kelly = self.calcular_kelly(80, precio_yes)
                            # Limitamos por nuestra regla de gestión de riesgo (max 10% del total)
                            fraccion_final = min(fraccion_kelly, RIESGO_MAX_POR_OPERACION)
                            monto_a_invertir = CAPITAL_TOTAL * fraccion_final

                            print(f"\n💎 OPORTUNIDAD EN {ciudad_key.upper()} [{nombre_rango}]")
                            print(f"   Precio: {precio_yes:.1f}% | Ventaja: {ventaja:.1f}%")
                            print(f"   💰 GESTIÓN DE RIESGO: Invertir ${monto_a_invertir:.2f} USDC")
                            
                            if not MODO_SIMULACION:
                                # Aquí iría la llamada a la API real: client.create_order(...)
                                print("   ⚡ EJECUTANDO COMPRA REAL EN BLOCKCHAIN...")
                            else:
                                print("   🧪 [SIMULACIÓN] Orden registrada en el diario.")
            except:
                continue

if __name__ == "__main__":
    bot = CryptoWeatherBot()
    bot.escanear_y_operar()
