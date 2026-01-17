import requests
import json
from datetime import datetime, timedelta

def run_simulation():
    print(f"--- 🧪 SIMULACIÓN MEJORADA: {datetime.now()} ---")
    
    # 1. CLIMA PARA MAÑANA
    mañana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    prob_real = 0
    try:
        r_weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": 40.78, "longitude": -73.97, "daily": "precipitation_probability_max", "timezone": "America/New_York", "start_date": mañana, "end_date": mañana}
        )
        prob_real = r_weather.json()['daily']['precipitation_probability_max'][0]
        print(f"🌦️ Probabilidad Satélite ({mañana}): {prob_real}%")
    except:
        print("❌ Error clima")

    # 2. BÚSQUEDA INTELIGENTE EN POLYMARKET
    precio_mercado = 0
    nombre_encontrado = ""
    
    try:
        # Buscamos "Rain" y filtramos nosotros
        url = "https://gamma-api.polymarket.com/events?q=Rain&closed=false"
        r_poly = requests.get(url)
        eventos = r_poly.json()
        
        for e in eventos:
            titulo = e.get('title', '')
            # Buscamos que sea de NYC y de la fecha de mañana (Jan 18)
            if ("NYC" in titulo or "New York" in titulo) and "Jan" in titulo:
                markets = e.get('markets', [])
                if markets:
                    prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                    precio_mercado = float(prices[0]) * 100
                    nombre_encontrado = titulo
                    break

        if nombre_encontrado:
            print(f"📊 Mercado: {nombre_encontrado}")
            print(f"💰 Precio: {precio_mercado}%")
        else:
            print("⚠️ No encontré el mercado de mañana en Polymarket.")

    except Exception as err:
        print(f"❌ Error API: {err}")

    # 3. DECISIÓN FINAL
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*30)
        print(f"DIFERENCIA (EDGE): {ventaja:.2f}%")
        if ventaja > 10:
            print("💰 ACCIÓN: COMPRARÍA 'YES'")
        elif ventaja < -10:
            print("📉 ACCIÓN: NO COMPRARÍA (Caro)")
        else:
            print("⚖️ ACCIÓN: ESPERAR (Precio justo)")
        print("="*30)

if __name__ == "__main__":
    run_simulation()
