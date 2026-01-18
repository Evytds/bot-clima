import requests
import json
import re
from datetime import datetime

def run_simulation():
    print(f"--- 🚀 BOT ANALISTA DE ÉLITE (LIVE 18 ENERO): {datetime.now()} ---")
    
    # 1. LISTA DE OBJETIVOS (Slugs confirmados para hoy 18 de Enero)
    objetivos = [
        "highest-temperature-in-seoul-on-january-18",
        "highest-temperature-in-atlanta-on-january-18",
        "highest-temperature-in-nyc-on-january-18",
        "highest-temperature-in-london-on-january-18",
        "highest-temperature-in-toronto-on-january-18"
    ]

    ciudades_coords = {
        "seoul": [37.56, 126.97, "celsius"],
        "atlanta": [33.74, -84.38, "fahrenheit"],
        "nyc": [40.71, -74.00, "fahrenheit"],
        "london": [51.50, -0.12, "celsius"],
        "toronto": [43.65, -79.38, "celsius"]
    }

    encontrados = 0

    for slug in objetivos:
        try:
            # Ir directo al evento por su nombre único (Slug)
            url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
            r = requests.get(url)
            if r.status_code != 200: continue
            
            ev = r.json()
            titulo = ev.get('title', slug)
            print(f"\n🎯 ANALIZANDO: {titulo}")

            # Identificar ciudad para el clima
            ciudad_key = slug.split('-')[3] # Extrae 'seoul', 'nyc', etc.
            lat, lon, unidad = ciudades_coords[ciudad_key]

            # CONSULTA CLIMA REAL (Open-Meteo)
            res_w = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_max", "temperature_unit": unidad, "timezone": "auto", "forecast_days": 1}
            ).json()
            temp_real = res_w['daily']['temperature_2m_max'][0]
            print(f"🌡️ Satélite dice: {temp_real}°{'F' if unidad == 'fahrenheit' else 'C'}")

            # Analizar cada rango de temperatura dentro de ese mercado
            for m in ev.get('markets', []):
                nombre_rango = m.get('groupItemTitle', 'Rango')
                precios = json.loads(m.get('outcomePrices', '["0", "0"]'))
                precio_yes = float(precios[0]) * 100
                
                # Extraer números del rango (ej: "34-35" -> [34, 35])
                nums = [int(n) for n in re.findall(r'\d+', nombre_rango)]
                
                es_probable = False
                if len(nums) >= 2:
                    es_probable = nums[0] <= temp_real <= nums[1]
                elif len(nums) == 1:
                    es_probable = round(temp_real) == nums[0]

                # SEÑAL DE TRADING
                if es_probable and precio_yes < 30:
                    print(f"   🔥 GANANCIA DETECTADA: [{nombre_rango}] Precio {precio_yes}% | ¡HUBIERA COMPRADO!")
                elif not es_probable and precio_yes > 70:
                    print(f"   🛡️ COBERTURA: [{nombre_rango}] Precio {precio_yes}% | ¡HUBIERA COMPRADO 'NO'!")
            
            encontrados += 1

        except Exception as e:
            continue

    if encontrados == 0:
        print("📭 Los mercados directos no respondieron. Intentando búsqueda por TAG 'Weather'...")
        # Búsqueda alternativa por categoría 'Weather'
        try:
            r_alt = requests.get("https://gamma-api.polymarket.com/events?active=true&closed=false&q=weather&limit=50")
            for ev in r_alt.json():
                print(f"👉 Encontrado mercado alternativo: {ev.get('title')}")
        except:
            print("❌ Error total de conexión.")

if __name__ == "__main__":
    run_simulation()
