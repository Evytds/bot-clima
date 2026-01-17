import requests
import json
from datetime import datetime
import os

def run_bot():
    print(f"--- 🔄 EJECUTANDO BOT: {datetime.now()} ---")
    
    # 1. Obtener Clima NY
    try:
        r_weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": 40.78, "longitude": -73.97, "daily": "precipitation_sum", "timezone": "America/New_York"}
        )
        rain_mm = r_weather.json()['daily']['precipitation_sum'][0]
    except:
        rain_mm = "Error"

    # 2. Obtener Precio Polymarket (Buscando 'Rain')
    price = "No encontrado"
    market_name = "N/A"
    
    try:
        r_poly = requests.get("https://gamma-api.polymarket.com/events", params={"q": "Rain", "closed": "false"})
        events = r_poly.json()
        for event in events:
            title = event.get('title', '')
            # Buscamos algo que parezca el mercado de NY
            if "Rain" in title and "New York" in title:
                markets = event.get('markets', [])
                if markets:
                    prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                    price = prices[0] # Precio del YES
                    market_name = title
                    break
    except Exception as e:
        print(f"Error Poly: {e}")

    # 3. IMPRIMIR RESULTADO (Esto quedará guardado en el Log de GitHub)
    print(f"📍 Mercado: {market_name}")
    print(f"💰 Precio YES: {price}")
    print(f"☔ Lluvia Pronosticada: {rain_mm} mm")
    
    # Un hack para guardar datos: Imprimimos en formato CSV en la consola
    print(f"CSV_DATA,{datetime.now()},{market_name},{price},{rain_mm}")

if __name__ == "__main__":
    run_bot()
