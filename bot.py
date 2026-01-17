import requests
import json
from datetime import datetime, timedelta

def run_simulation():
    print(f"--- 🕵️ CAZADOR DE MERCADOS + SIMULACIÓN: {datetime.now()} ---")
    
    # 1. CLIMA (CIENCIA)
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
        print("❌ Error obteniendo datos del clima")

    # 2. BÚSQUEDA DINÁMICA DE MERCADO
    precio_mercado = 0
    mercado_encontrado = None
    # Probamos varias búsquedas para forzar a Polymarket a soltar el dato
    busquedas = ["Rain NYC", "Rain New York", "Precipitation NYC"]
    
    for query in busquedas:
        if mercado_encontrado: break
        try:
            url = f"https://gamma-api.polymarket.com/events?q={query}&active=true&closed=false"
            r = requests.get(url)
            eventos = r.json()
            for e in eventos:
                titulo = e.get('title', '').lower()
                # Buscamos que diga 'rain', que sea en 'ny' y que sea para el '18'
                if "rain" in titulo and ("nyc" in titulo or "new york" in titulo) and "18" in titulo:
                    mercado_encontrado = e
                    break
        except:
            continue

    if mercado_encontrado:
        titulo = mercado_encontrado.get('title')
        markets = mercado_encontrado.get('markets', [])
        if markets:
            prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
            precio_mercado = float(prices[0]) * 100
            print(f"✅ ¡MERCADO LOCALIZADO!: {titulo}")
            print(f"💰 Precio actual del 'YES': {precio_mercado}%")
    else:
        print("⚠️ No pude encontrar el mercado automáticamente.")
        print("💡 Tip: A veces Polymarket los activa unas horas antes del evento.")

    # 3. ANÁLISIS DE RENTABILIDAD
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"🔍 VENTAJA DETECTADA (EDGE): {ventaja:.2f}%")
        
        if ventaja > 10:
            print("💰 SIMULACIÓN: ¡COMPRARÍA 'YES' AHORA!")
            print(f"Justificación: La ciencia ({prob_real}%) es muy superior al precio ({precio_mercado}%)")
        elif ventaja < -10:
            print("📉 SIMULACIÓN: DEMASIADO CARO.")
            print("Justificación: No hay ventaja estadística para comprar.")
        else:
            print("⚖️ SIMULACIÓN: ESPERAR.")
            print("Justificación: El precio es justo según los satélites.")
        print("="*40 + "\n")

if __name__ == "__main__":
    run_simulation()
