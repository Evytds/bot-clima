import requests
import json
from datetime import datetime

def run_simulation():
    print(f"--- 🌡️ BOT ANALISTA DE TEMPERATURAS: {datetime.now()} ---")
    
    # 1. BASE DE DATOS DE CIUDADES (Coordenadas para el satélite)
    ciudades = {
        "Seattle": {"lat": 47.60, "lon": -122.33},
        "Seoul": {"lat": 37.56, "lon": 126.97},
        "New York": {"lat": 40.71, "lon": -74.00},
        "Toronto": {"lat": 43.65, "lon": -79.38}
    }

    # 2. ESCANEO GLOBAL DE MERCADOS DE TEMPERATURA
    try:
        url_poly = "https://gamma-api.polymarket.com/markets?active=true&limit=100&q=temperature"
        r = requests.get(url_poly)
        mercados = r.json()
        
        print(f"🔍 Analizando {len(mercados)} mercados de temperatura activos...\n")

        for m in mercados:
            titulo = m.get('question', '')
            
            # Buscamos qué ciudad de nuestra lista está en el mercado
            for ciudad, coords in ciudades.items():
                if ciudad in titulo:
                    # OBTENER CLIMA REAL PARA ESA CIUDAD
                    res = requests.get(
                        "https://api.open-meteo.com/v1/forecast",
                        params={
                            "latitude": coords['lat'], "longitude": coords['lon'],
                            "daily": "temperature_2m_max", "timezone": "auto", "forecast_days": 1
                        }
                    )
                    temp_max_cientifica = res.json()['daily']['temperature_2m_max'][0]
                    
                    # PRECIO EN POLYMARKET
                    precios_raw = m.get('outcomePrices')
                    if precios_raw:
                        precio_yes = float(precios_raw[0]) * 100
                        
                        print(f"📍 CIUDAD: {ciudad}")
                        print(f"📊 Mercado: {titulo}")
                        print(f"🌡️ Pronóstico Satélite: {temp_max_cientifica}°C / (Convierte a °F si es necesario)")
                        print(f"💰 Precio 'YES': {precio_yes}%")
                        
                        # LÓGICA DE DECISIÓN SIMPLE
                        # (Aquí el bot debería ver si la temp_max cae dentro del rango del título)
                        print("⚖️ Estado: Analizando rango... [SIMULACIÓN]")
                        print("-" * 30)

    except Exception as e:
        print(f"❌ Error en el escaneo: {e}")

if __name__ == "__main__":
    run_simulation()
