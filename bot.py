import requests
import json
import re
from datetime import datetime

def extraer_datos_mercado(texto):
    # Extrae todos los números (rango o temperatura única)
    nums = re.findall(r'\d+', texto)
    return [int(n) for n in nums]

def run_simulation():
    print(f"--- 📡 ESCÁNER DE TEMPERATURAS GLOBAL: {datetime.now()} ---")
    
    # Base de datos ampliada (las que opera tu 'pro')
    ciudades = {
        "Seoul": {"lat": 37.56, "lon": 126.97},
        "Atlanta": {"lat": 33.74, "lon": -84.38},
        "Buenos Aires": {"lat": -34.60, "lon": -58.38},
        "New York": {"lat": 40.71, "lon": -74.00},
        "Seattle": {"lat": 47.60, "lon": -122.33},
        "Toronto": {"lat": 43.65, "lon": -79.38}
    }

    try:
        # 1. ESCANEO TOTAL (Sin depender del buscador de Poly)
        url = "https://gamma-api.polymarket.com/markets?active=true&limit=100&order=volume&dir=desc"
        mercados = requests.get(url).json()
        print(f"🔎 Revisando {len(mercados)} mercados activos...")

        encontrados = 0
        for m in mercados:
            titulo = m.get('question', '')
            # Buscamos mercados de temperatura máxima
            if "highest temperature" in titulo.lower():
                encontrados += 1
                for ciudad, coords in ciudades.items():
                    if ciudad.lower() in titulo.lower():
                        # 2. OBTENER CLIMA (Detectar si es °F o °C por el título)
                        unidad = "fahrenheit" if "°F" in titulo or "Fahrenheit" in titulo else "celsius"
                        
                        res = requests.get(
                            "https://api.open-meteo.com/v1/forecast",
                            params={
                                "latitude": coords['lat'], "longitude": coords['lon'],
                                "daily": "temperature_2m_max", "temperature_unit": unidad,
                                "timezone": "auto", "forecast_days": 1
                            }
                        ).json()
                        
                        temp_real = res['daily']['temperature_2m_max'][0]
                        rango = extraer_datos_mercado(titulo)
                        
                        # Extraer precio del YES
                        precios = json.loads(m.get('outcomePrices', '["0", "0"]'))
                        precio_yes = float(precios[0]) * 100

                        # 3. LÓGICA DE ACIERTO
                        dentro_del_rango = False
                        if len(rango) >= 2: # Ej: 38-39
                            dentro_del_rango = rango[0] <= temp_real <= rango[1]
                        elif len(rango) == 1: # Ej: 3°C
                            dentro_del_rango = round(temp_real) == rango[0]

                        print(f"\n📍 {ciudad} | {titulo}")
                        print(f"🌡️ Pronóstico: {temp_real}°{'F' if unidad == 'fahrenheit' else 'C'}")
                        print(f"💰 Precio 'YES': {precio_yes}%")

                        if dentro_del_rango and precio_yes < 40:
                            print("🚀 SEÑAL: ¡VENTAJA DETECTADA! Compraría YES.")
                        elif not dentro_del_rango and precio_yes > 60:
                            print("📉 SEÑAL: ¡VENTAJA DETECTADA! Compraría NO.")
                        else:
                            print("⚖️ SEÑAL: Esperar mejor precio.")
        
        if encontrados == 0:
            print("📭 No se encontraron mercados de temperatura en este momento.")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_simulation()
