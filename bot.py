import requests
import json
from datetime import datetime
import os

def run_bot():
    print(f"--- 🤖 BOT VIGILANTE: {datetime.now()} ---")
    
    # 1. OBTENER CLIMA (Siempre funciona)
    rain_mm = 0
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": 40.78, "longitude": -73.97, "daily": "precipitation_sum", "timezone": "America/New_York"}
        )
        rain_mm = r.json()['daily']['precipitation_sum'][0]
        print(f"🌦️ Pronóstico Lluvia NY: {rain_mm} mm")
    except:
        print("⚠️ Error leyendo clima")

    # 2. BUSCAR MERCADO (Intento Universal)
    market_name = "No encontrado hoy"
    price_yes = 0.0
    found = False
    
    try:
        # Buscamos 'New York' general para ver si aparece algo de clima
        r = requests.get("https://gamma-api.polymarket.com/events", params={"q": "New York", "closed": "false", "limit": 50})
        events = r.json()
        
        for event in events:
            title = event.get('title', '')
            # Buscamos palabras clave de clima dentro de los resultados de NY
            if "Rain" in title or "Precipitation" in title or "snow" in title:
                markets = event.get('markets', [])
                if markets:
                    prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                    price_yes = prices[0]
                    market_name = title
                    found = True
                    print(f"🎯 ¡MERCADO DETECTADO!: {market_name} | Precio: {price_yes}")
                    break
    except Exception as e:
        print(f"❌ Error API: {e}")

    # 3. GUARDAR DATOS (Solo si encontró mercado o si quieres loguear clima igual)
    # Formato CSV simple para que se guarde en el registro
    print(f"CSV_LOG,{datetime.now()},{market_name},{price_yes},{rain_mm}")

    if not found:
        print("💤 No hay mercado de lluvia activo en este momento. Reintentando en 1 hora...")

if __name__ == "__main__":
    run_bot()
