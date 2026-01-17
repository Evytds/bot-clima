import requests
import json
from datetime import datetime, timedelta

def run_simulation():
    print(f"--- 🚀 BOT ANALISTA (FILTRO REAL): {datetime.now()} ---")
    
    # 1. CLIMA (CIENCIA) - Esto ya lo tienes dominado
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

    # 2. BÚSQUEDA SIN "RUIDO" EN POLYMARKET
    precio_mercado = 0
    mercado_encontrado = None
    
    print("🔍 Escaneando mercados activos de NYC...")
    
    try:
        # Buscamos 'NYC' directamente, que suele ser más limpio que 'Rain'
        url = "https://gamma-api.polymarket.com/events?q=NYC&active=true&closed=false"
        r = requests.get(url)
        eventos = r.json()
        
        for e in eventos:
            titulo = e.get('title', '')
            # Buscamos que sea de LLUVIA y que sea para mañana (18)
            if ("Rain" in titulo or "Precipitation" in titulo) and "18" in titulo:
                markets = e.get('markets', [])
                if markets:
                    prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                    precio_mercado = float(prices[0]) * 100
                    mercado_encontrado = titulo
                    break

        if mercado_encontrado:
            print(f"✅ ¡MERCADO DETECTADO!: {mercado_encontrado}")
            print(f"💰 Precio actual del 'YES': {precio_mercado}%")
        else:
            print("⚠️ No encontré el mercado de NYC para mañana. Es posible que aún no esté listado en la API pública.")

    except Exception as err:
        print(f"❌ Error en la API: {err}")

    # 3. EL ANÁLISIS DE RENTABILIDAD
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"🔍 VENTAJA (EDGE): {ventaja:.2f}%")
        if ventaja > 10:
            print("💰 ACCIÓN: COMPRARÍA 'YES'")
            print(f"Razón: El satélite dice {prob_real}% y el precio es solo {precio_mercado}%")
        elif ventaja < -10:
            print("📉 ACCIÓN: NO COMPRARÍA")
            print("Razón: El precio es demasiado alto para la probabilidad real.")
        else:
            print("⚖️ ACCIÓN: ESPERAR")
        print("="*40)

if __name__ == "__main__":
    run_simulation()
