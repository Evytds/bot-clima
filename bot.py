import requests
import json
import re
from datetime import datetime

def extraer_rango(texto):
    # Busca números en el título (ej: "38-39" o "3")
    numeros = re.findall(r'\d+', texto)
    return [int(n) for n in numeros]

def run_simulation():
    print(f"--- 🌡️ ANALISTA DE RANGOS PRO: {datetime.now()} ---")
    
    ciudades = {
        "Seoul": {"lat": 37.56, "lon": 126.97, "unit": "celsius"},
        "Atlanta": {"lat": 33.74, "lon": -84.38, "unit": "fahrenheit"},
        "Buenos Aires": {"lat": -34.60, "lon": -58.38, "unit": "celsius"}
    }

    try:
        # 1. ESCANEO DE MERCADOS DE TEMPERATURA
        url = "https://gamma-api.polymarket.com/markets?active=true&limit=100&q=temperature"
        mercados = requests.get(url).json()

        for m in mercados:
            titulo = m.get('question', '')
            for ciudad, info in ciudades.items():
                if ciudad in titulo:
                    # 2. OBTENER CLIMA CIENTÍFICO
                    params = {
                        "latitude": info['lat'], "longitude": info['lon'],
                        "daily": "temperature_2m_max", "timezone": "auto", "forecast_days": 1
                    }
                    if info['unit'] == "fahrenheit":
                        params["temperature_unit"] = "fahrenheit"
                    
                    res = requests.get("https://api.open-meteo.com/v1/forecast", params=params).json()
                    temp_max_real = res['daily']['temperature_2m_max'][0]

                    # 3. ANALIZAR EL RANGO DEL MERCADO
                    rango = extraer_rango(titulo)
                    precio_yes = float(m.get('outcomePrices', '["0"]')[0]) * 100
                    
                    # Lógica de acierto: ¿Está la temperatura real dentro del rango?
                    exito = False
                    if len(rango) == 2: # Caso rango 38-39
                        exito = rango[0] <= temp_max_real <= rango[1]
                    elif len(rango) == 1: # Caso exacto 3°C
                        exito = round(temp_max_real) == rango[0]

                    print(f"📍 {ciudad} | {titulo}")
                    print(f"🌡️ Pronóstico: {temp_max_real}{'°F' if info['unit'] == 'fahrenheit' else '°C'}")
                    print(f"💰 Precio Mercado: {precio_yes}%")
                    
                    # 4. DECISIÓN DE INVERSIÓN
                    if exito and precio_yes < 40:
                        print("🚀 SEÑAL: COMPRAR 'YES' (Está barato y el clima coincide)")
                    elif not exito and precio_yes > 60:
                        print("📉 SEÑAL: COMPRAR 'NO' (El clima dice que no pasará y el precio es alto)")
                    else:
                        print("⚖️ SEÑAL: ESPERAR")
                    print("-" * 40)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_simulation()
