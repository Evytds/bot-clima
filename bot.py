import requests
import json
import re
import os
import csv
from datetime import datetime

# ARCHIVO PARA GUARDAR EL HISTORIAL
HISTORIAL_FILE = "historial_ganancias.csv"

def guardar_operacion(ciudad, mercado, pronostico, precio, tipo):
    # Si el archivo no existe, creamos la cabecera
    file_exists = os.path.isfile(HISTORIAL_FILE)
    with open(HISTORIAL_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Fecha', 'Ciudad', 'Mercado', 'Pronostico', 'Precio_Compra', 'Tipo'])
        
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ciudad, mercado, pronostico, f"{precio:.2f}%", tipo
        ])

def run_simulation():
    print(f"--- 🚀 BOT ANALISTA CON DIARIO: {datetime.now()} ---")
    
    # 1. OBJETIVOS CONFIRMADOS
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

    for slug in objetivos:
        try:
            url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
            r = requests.get(url)
            if r.status_code != 200: continue
            
            ev = r.json()
            ciudad_key = slug.split('-')[3]
            lat, lon, unidad = ciudades_coords[ciudad_key]

            # CLIMA REAL
            res_w = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_max", "temperature_unit": unidad, "timezone": "auto", "forecast_days": 1}
            ).json()
            temp_real = res_w['daily']['temperature_2m_max'][0]

            for m in ev.get('markets', []):
                nombre_rango = m.get('groupItemTitle', 'Rango')
                precios = json.loads(m.get('outcomePrices', '["0", "0"]'))
                precio_yes = float(precios[0]) * 100
                
                nums = [int(n) for n in re.findall(r'\d+', nombre_rango)]
                es_probable = False
                if len(nums) >= 2:
                    es_probable = nums[0] <= temp_real <= nums[1]
                elif len(nums) == 1:
                    es_probable = round(temp_real) == nums[0]

                # SEÑAL Y REGISTRO
                if es_probable and precio_yes < 30:
                    print(f"🔥 REGISTRANDO COMPRA: {slug} [{nombre_rango}]")
                    guardar_operacion(ciudad_key.upper(), nombre_rango, temp_real, precio_yes, "YES")
                elif not es_probable and precio_yes > 75:
                    print(f"🛡️ REGISTRANDO COBERTURA: {slug} [{nombre_rango}]")
                    guardar_operacion(ciudad_key.upper(), nombre_rango, temp_real, precio_yes, "NO")
            
        except Exception as e:
            continue

if __name__ == "__main__":
    run_simulation()
