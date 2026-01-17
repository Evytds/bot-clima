import requests
import json
from datetime import datetime, timedelta

def run_simulation():
    print(f"--- 🕵️ SUPER DEBUG + SIMULACIÓN: {datetime.now()} ---")
    
    # 1. CLIMA (CIENCIA) - ¡ESTO YA FUNCIONA!
    fecha_objetivo = "2026-01-18"
    prob_real = 0
    try:
        r_weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": 40.78, "longitude": -73.97, "daily": "precipitation_probability_max", "timezone": "America/New_York", "start_date": fecha_objetivo, "end_date": fecha_objetivo}
        )
        prob_real = r_weather.json()['daily']['precipitation_probability_max'][0]
        print(f"🌦️ Probabilidad Satélite ({fecha_objetivo}): {prob_real}%")
    except:
        print("❌ Error clima")

    # 2. RED DE ARRASTRE (POLYMARKET)
    print("\n🔍 BUSCANDO MERCADOS DISPONIBLES...")
    precio_mercado = 0
    try:
        # Pedimos los 50 mercados más recientes que contengan "Rain"
        url = "https://gamma-api.polymarket.com/events?q=Rain&active=true&limit=50"
        r = requests.get(url)
        eventos = r.json()
        
        print(f"📦 Se encontraron {len(eventos)} mercados relacionados con 'Rain'.")
        
        for e in eventos:
            titulo = e.get('title', 'Sin título')
            print(f"👉 Encontrado: {titulo}") # Esto nos dirá el nombre exacto
            
            # Si el título tiene NYC o New York y el número 18, lo tomamos
            if ("NYC" in titulo or "New York" in titulo) and "18" in titulo:
                markets = e.get('markets', [])
                if markets:
                    prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                    precio_mercado = float(prices[0]) * 100
                    print(f"🎯 ¡ESTE ES EL NUESTRO!: {titulo} | Precio: {precio_mercado}%")
                    break

    except Exception as err:
        print(f"❌ Error en la API: {err}")

    # 3. ANÁLISIS
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"🔍 VENTAJA (EDGE): {ventaja:.2f}%")
        if ventaja > 10:
            print("💰 ACCIÓN: COMPRARÍA 'YES'")
        elif ventaja < -10:
            print("📉 ACCIÓN: NO COMPRARÍA")
        else:
            print("⚖️ ACCIÓN: ESPERAR")
        print("="*40)
    else:
        print("\n⚠️ No se pudo realizar la simulación porque no hay coincidencia exacta.")
        print("Revisa la lista de arriba y dime cuál es el nombre que aparece para Nueva York.")

if __name__ == "__main__":
    run_simulation()
