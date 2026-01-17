import requests
import json
from datetime import datetime

def run_simulation():
    # ID EXTRAÍDO DE TU LINK
    EVENT_ID = "1760165563991" 
    
    print(f"--- 🎯 EJECUCIÓN DIRECTA POR ID: {datetime.now()} ---")
    
    # 1. CLIMA (Satélite)
    prob_real = 0
    try:
        r_weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 40.78, "longitude": -73.97, 
                "daily": "precipitation_probability_max", 
                "timezone": "America/New_York",
                "start_date": "2026-01-18", "end_date": "2026-01-18"
            }
        )
        prob_real = r_weather.json()['daily']['precipitation_probability_max'][0]
        print(f"🌦️ Probabilidad Satélite (18 Ene): {prob_real}%")
    except:
        print("❌ Error clima")

    # 2. MERCADO (Conexión Directa)
    precio_mercado = 0
    try:
        # Consultamos el ID directamente, sin usar buscadores
        url = f"https://gamma-api.polymarket.com/events/{EVENT_ID}"
        r = requests.get(url)
        data = r.json()
        
        titulo = data.get('title', 'Mercado de Lluvia NYC')
        markets = data.get('markets', [])
        
        if markets:
            # Obtenemos el precio del 'YES'
            prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
            precio_mercado = float(prices[0]) * 100
            print(f"✅ MERCADO DETECTADO: {titulo}")
            print(f"💰 Precio actual del 'YES': {precio_mercado}%")
        else:
            print("⚠️ El mercado existe pero no tiene precios aún.")

    except Exception as e:
        print(f"❌ Error al conectar con Polymarket ID: {e}")

    # 3. RESULTADO DE LA ESTRATEGIA
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"🔍 VENTAJA (EDGE): {ventaja:.2f}%")
        
        if ventaja > 10:
            print("🚀 SEÑAL: COMPRARÍA 'YES' (Muy barato)")
        elif ventaja < -10:
            print("📉 SEÑAL: NO COMPRAR / VENDER 'YES' (Muy caro)")
        else:
            print("⚖️ SEÑAL: ESPERAR (Precio justo)")
        print("="*40 + "\n")
    else:
        print("\n⚠️ No se pudo calcular la ventaja por falta de datos del mercado.")

if __name__ == "__main__":
    run_simulation()
