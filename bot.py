import requests
import json
from datetime import datetime, timedelta

def run_simulation():
    print(f"--- 🧪 MODO SIMULACIÓN ACTIVO: {datetime.now()} ---")
    
    # 1. PRONÓSTICO PARA MAÑANA (18 de enero)
    # Buscamos el pronóstico específico para la fecha del mercado
    try:
        mañana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        r_weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 40.78, 
                "longitude": -73.97, 
                "daily": "precipitation_probability_max", 
                "timezone": "America/New_York",
                "start_date": mañana,
                "end_date": mañana
            }
        )
        prob_real = r_weather.json()['daily']['precipitation_probability_max'][0]
        print(f"🌦️ Pronóstico Científico para el {mañana}: {prob_real}% de prob. de lluvia.")
    except Exception as e:
        print(f"❌ Error clima: {e}")
        prob_real = 0

    # 2. PRECIO EN POLYMARKET
    # Usamos el 'slug' que sacamos de tu link
    slug = "will-it-rain-in-nyc-on-january-18"
    precio_mercado = 0
    try:
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        r_poly = requests.get(url)
        data = r_poly.json()
        
        if data:
            markets = data[0].get('markets', [])
            prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
            precio_mercado = float(prices[0]) * 100 # Convertimos a porcentaje (ej: 0.55 -> 55%)
            print(f"📊 Precio en Polymarket: {precio_mercado}%")
    except:
        print("⚠️ No se pudo obtener el precio del mercado.")

    # 3. LÓGICA DE DECISIÓN (Sin gastar dinero)
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print(f"⚖️ Ventaja Detectada: {ventaja:.2f}%")
        
        print("\n" + "="*40)
        if ventaja > 10:
            print("💰 RESULTADO: ¡COMPRARÍA 'YES' AHORA!")
            print(f"Razón: La ciencia dice {prob_real}% y el mercado solo paga {precio_mercado}%")
        elif ventaja < -10:
            print("🚫 RESULTADO: NO COMPRARÍA.")
            print("Razón: El mercado está demasiado caro para el riesgo.")
        else:
            print("😐 RESULTADO: ESPERAR.")
            print("Razón: El precio es justo, no hay ventaja clara.")
        print("="*40 + "\n")

if __name__ == "__main__":
    run_simulation()
