import requests
import json
from datetime import datetime

def run_simulation():
    # ID directo de tu link
    EVENT_ID = "1760165563991" 
    
    print(f"--- 🚀 EXTRACCIÓN PROFUNDA DE DATOS: {datetime.now()} ---")
    
    # 1. CLIMA (CIENCIA)
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
        print(f"🌦️ Probabilidad Satélite: {prob_real}%")
    except:
        print("❌ Error clima")

    # 2. MERCADO (Búsqueda Exhaustiva de Precio)
    precio_mercado = 0
    try:
        url = f"https://gamma-api.polymarket.com/events/{EVENT_ID}"
        r = requests.get(url)
        data = r.json()
        
        markets = data.get('markets', [])
        if markets:
            m = markets[0]
            # Intentamos 3 formas de obtener el precio si una falla
            raw_prices = m.get('outcomePrices')
            last_price = m.get('lastTradePrice')
            best_bid = m.get('bestBid')
            
            if raw_prices and raw_prices != 'null':
                precio_mercado = float(json.loads(raw_prices)[0]) * 100
            elif last_price:
                precio_mercado = float(last_price) * 100
            elif best_bid:
                precio_mercado = float(best_bid) * 100
                
            print(f"✅ MERCADO: {data.get('title')}")
            print(f"💰 Precio Detectado: {precio_mercado}%")
        else:
            print("⚠️ No se encontraron mercados dentro del evento.")

    except Exception as e:
        print(f"❌ Error de conexión: {e}")

    # 3. LÓGICA DE RENTABILIDAD
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"🔍 ANÁLISIS DE VENTAJA: {ventaja:.2f}%")
        
        if ventaja > 10:
            print("🚀 SEÑAL: ¡GANANCIA PROBABLE! El mercado está muy barato.")
            print(f"Hubieras comprado a {precio_mercado}% algo que tiene {prob_real}% de éxito.")
        elif ventaja < -10:
            print("📉 SEÑAL: EVITAR. El mercado está muy caro.")
        else:
            print("⚖️ SEÑAL: PRECIO EQUILIBRADO.")
        print("="*40 + "\n")
    else:
        print("\n⚠️ Datos insuficientes para calcular rentabilidad.")

if __name__ == "__main__":
    run_simulation()
