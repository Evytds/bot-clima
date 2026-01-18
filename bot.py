import requests
import json
import re
import os
from datetime import datetime

# === PARÁMETROS DE GESTIÓN DE RIESGO Y COSTOS ===
ARCHIVO_BILLETERA = "billetera_virtual.json"
FEES_PLATAFORMA = 0.002    # 0.2% comisión Polymarket
GAS_POLYGON = 0.01        # Costo estimado de gas en USDC
SLIPPAGE_ADAPTATIVO = 0.01 # 1% de margen por movimiento de precio
RIESGO_MAX_POR_OP = 0.15  # Máximo 15% del capital por operación
UMBRAL_VENTAJA_NETA = 10.0 # Ventaja mínima tras descontar comisiones
MODO_SIMULACION = True    # Cambiar a False para ejecutar con API Real

class SistemaMaestroTrader:
    def __init__(self):
        self.capital = self.cargar_billetera()
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
            "nyc": [40.71, -74.00, "fahrenheit"],
            "london": [51.50, -0.12, "celsius"],
            "toronto": [43.65, -79.38, "celsius"]
        }

    def cargar_billetera(self):
        if os.path.exists(ARCHIVO_BILLETERA):
            with open(ARCHIVO_BILLETERA, 'r') as f:
                return json.load(f).get("balance", 50.0)
        return 50.0

    def guardar_billetera(self, nuevo_balance):
        self.capital = nuevo_balance
        with open(ARCHIVO_BILLETERA, 'w') as f:
            json.dump({"balance": nuevo_balance, "ultima_actualizacion": str(datetime.now())}, f)

    def calcular_kelly(self, prob_real, precio_mercado):
        p = prob_real / 100.0
        precio_ajustado = (precio_mercado / 100.0) * (1 + SLIPPAGE_ADAPTATIVO)
        if precio_ajustado <= 0 or precio_ajustado >= 1: return 0
        b = (1 / precio_ajustado) - 1
        q = 1 - p
        f_star = (p * b - q) / b
        return max(0, f_star)

    def obtener_clima(self, lat, lon, unidad):
        try:
            # Consultamos para hoy 18 de Enero (según el contexto actual)
            res = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_max", 
                        "temperature_unit": unidad, "timezone": "auto", "forecast_days": 1}
            ).json()
            return res['daily']['temperature_2m_max'][0]
        except: return None

    def ejecutar_ciclo(self):
        print(f"--- 🚀 SISTEMA MAESTRO ACTIVO | CAPITAL: ${self.capital:.2f} USDC ---")
        
        # Slugs para hoy 18 de Enero
        objetivos = [f"highest-temperature-in-{c}-on-january-18" for c in self.ciudades.keys()]
        
        for slug in objetivos:
            try:
                url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
                r = requests.get(url)
                if r.status_code != 200: continue
                
                ev = r.json()
                ciudad_key = slug.split('-')[3]
                lat, lon, unidad = self.ciudades[ciudad_key]
                temp_real = self.obtener_clima(lat, lon, unidad)

                for m in ev.get('markets', []):
                    # Extraer precio y rango
                    precios = json.loads(m.get('outcomePrices', '["0", "0"]'))
                    precio_yes = float(precios[0]) * 100
                    rango_txt = m.get('groupItemTitle', 'Rango')
                    
                    # Lógica de acierto científico
                    nums = [int(n) for n in re.findall(r'\d+', rango_txt)]
                    acierto = (nums[0] <= temp_real <= nums[1]) if len(nums)==2 else (round(temp_real)==nums[0])
                    
                    if acierto:
                        # 1. CÁLCULO DE FEES Y VENTAJA REAL
                        precio_real_compra = precio_yes * (1 + SLIPPAGE_ADAPTATIVO + FEES_PLATAFORMA)
                        ventaja_neta = 85 - precio_real_compra # Asumimos 85% confianza satélite
                        
                        if ventaja_neta >= UMBRAL_VENTAJA_NETA:
                            # 2. GESTIÓN DE RIESGO (KELLY)
                            f_kelly = self.calcular_kelly(85, precio_yes)
                            fraccion_final = min(f_kelly, RIESGO_MAX_POR_OP)
                            monto_inversion = self.capital * fraccion_final
                            
                            # Descontar Gas
                            monto_neto = monto_inversion - GAS_POLYGON
                            
                            if monto_neto > 0.5: # Evitar operaciones insignificantes
                                print(f"\n💎 OPORTUNIDAD: {slug} [{rango_txt}]")
                                print(f"   💰 Inversión Sugerida: ${monto_neto:.2f} USDC")
                                print(f"   📈 Ventaja Neta (inc. Fees): {ventaja_neta:.1f}%")
                                
                                if MODO_SIMULACION:
                                    # Simular Interés Compuesto: Si el bot acierta, el capital crece
                                    ganancia_estimada = (monto_neto / (precio_real_compra/100)) - monto_neto
                                    print(f"   🧪 [SIMULACIÓN] Ganancia potencial: +${ganancia_estimada:.2f} USDC")
                                    # Actualizamos la billetera para la próxima ciudad
                                    # (En una ejecución real, esto se haría tras el cierre del mercado)
            except: continue

if __name__ == "__main__":
    trader = SistemaMaestroTrader()
    trader.ejecutar_ciclo()
