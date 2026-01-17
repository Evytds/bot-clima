import requests
import json
import re
from datetime import datetime

def run_simulation():
    print(f"--- 🛰️ MOTOR DE TRADING CLIMÁTICO (ACTIVE SCAN): {datetime.now()} ---")
    
    # 1. ESCANEO DE ALTA PRECISIÓN (Events Endpoint)
    # Buscamos eventos activos (no cerrados) con un límite amplio
    url_poly = "https://gamma-api.polymarket.com/events?closed=false&limit=200&order=id&ascending=false"
    
    try:
        r = requests.get(url_poly)
        eventos = r.json()
        print(f"🔎 Analizando {len(eventos)} eventos en vivo...")

        encontrados = 0
        for ev in eventos:
            titulo = ev.get('title', '')
            
            # Filtro Maestro: Buscamos "Highest temperature"
            if "highest temperature" in titulo.lower():
                encontrados += 1
                
                # Extraemos Ciudad y Fecha del título
                # Ejemplo: "Highest temperature in Seoul on January 18?"
                ciudad = "Desconocida"
                if "Seoul" in titulo: ciudad = "Seoul"
                elif "Atlanta" in titulo: ciudad = "Atlanta"
                elif "NYC" in titulo or "New York" in titulo: ciudad = "New York City"
                elif "Buenos Aires" in titulo: ciudad = "Buenos Aires"

                # Si es una de nuestras ciudades, analizamos
                if ciudad != "Desconocida":
                    # Obtenemos Coordenadas
                    coords = {"Seoul": [37.56, 126.97], "Atlanta": [33.74, -84.38], "New York City": [40.71, -74.00], "Buenos Aires": [-34.60, -58.38]}
                    lat, lon = coords[ciudad]
                    
                    # 2. CONSULTA AL SATÉLITE (Open-Meteo)
                    unidad = "fahrenheit" if "°F" in titulo else "celsius"
                    res_weather = requests.get(
                        "https://api.open-meteo.com/v1/forecast",
                        params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_max", "temperature_unit": unidad, "timezone": "auto", "forecast_days": 2}
                    ).json()
                    
                    # Tomamos el pronóstico para mañana (Índice 1)
                    temp_real = res_weather['daily']['temperature_2m_max'][1]
                    
                    print(f"\n🎯 MERCADO: {titulo}")
                    print(f"🌡️ Pronóstico Científico: {temp_real}°{'F' if unidad == 'fahrenheit' else 'C'}")

                    # 3. EXTRAER PRECIOS DE CADA RANGO (Markets dentro del Evento)
                    for m in ev.get('markets', []):
                        nombre_opcion = m.get('groupItemTitle', 'Única')
                        precios = json.loads(m.get('outcomePrices', '["0", "0"]'))
                        precio_yes = float(precios[0]) * 100
                        
                        # Extraer números del rango (ej: "38-39" -> [38, 39])
                        numeros = [int(n) for n in re.findall(r'\d+', nombre_opcion)]
                        
                        # Lógica de decisión
                        es_ganadora = False
                        if len(numeros) == 2:
                            es_ganadora = numeros[0] <= temp_real <= numeros[1]
                        elif len(numeros) == 1:
                            es_ganadora = round(temp_real) == numeros[0]

                        if es_ganadora and precio_yes < 35:
                            print(f"   🔥 COMPRARÍA 'YES' en [{nombre_opcion}] a {precio_yes}% (GANANCIA PROBABLE)")
                        elif not es_ganadora and precio_yes > 70:
                            print(f"   🛡️ COMPRARÍA 'NO' en [{nombre_opcion}] a {100-precio_yes}% (COBERTURA)")

        if encontrados == 0:
            print("📭 Polymarket no tiene mercados de temperatura listados en los últimos 200 eventos.")

    except Exception as e:
        print(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    run_simulation()
