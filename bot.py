import requests
import json
from datetime import datetime
import os

def run_bot():
    print(f"--- 🚀 INICIANDO BOT FINAL: {datetime.now()} ---")
    
    # 1. OBTENER CLIMA (Open-Meteo)
    rain_mm = 0
    rain_prob = 0
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 40.78, 
                "longitude": -73.97, 
                "daily": "precipitation_sum,precipitation_probability_max", 
                "timezone": "America/New_York",
                "forecast_days": 1
            }
        )
        data = r.json()
        rain_mm = data['daily']['precipitation_sum'][0]
        rain_prob = data['daily']['precipitation_probability_max'][0]
        print(f"✅ Clima obtenido: {rain_mm}mm ({rain_prob}%)")
    except Exception as e:
        print(f"❌ Error Clima: {e}")

    # 2. OBTENER PRECIO POLYMARKET (Búsqueda Inteligente)
    market_found = False
    try:
        # Buscamos "Rain"
        r = requests.get("https://gamma-api.polymarket.com/events", params={"q": "Rain", "closed": "false", "limit": 20})
        events = r.json()
        
        for event in events:
            title = event.get('title', '')
            
            # LÓGICA INTELIGENTE: Busca "Rain" Y ("New York" O "NYC" O "Central Park")
            if "Rain" in title and ("New York" in title or "NYC" in title or "Central Park" in title):
                
                markets = event.get('markets', [])
                if markets:
                    prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                    price_yes = prices[0]
                    
                    print("\n" + "="*40)
                    print(f"🎯 MERCADO ENCONTRADO: {title}")
                    print(f"💰 PRECIO 'YES': {price_yes} USD")
                    print(f"☔ PRONÓSTICO: {rain_mm}mm")
                    print("="*40 + "\n")
                    
                    # Imprimir formato CSV para guardar
                    print(f"DATA_LOG,{datetime.now()},{title},{price_yes},{rain_mm},{rain_prob}")
                    market_found = True
                    break # Dejamos de buscar, ya encontramos el de hoy
        
        if not market_found:
            print("⚠️ No encontré el mercado de NY en la lista de hoy.")
            
    except Exception as e:
        print(f"❌ Error Poly: {e}")

if __name__ == "__main__":
    run_bot()
