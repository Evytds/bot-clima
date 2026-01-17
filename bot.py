import requests
import json
from datetime import datetime, timedelta

def run_simulation():
    print(f"--- 🧪 SIMULACIÓN (TIRO AL BLANCO): {datetime.now()} ---")
    
    # 1. CLIMA PARA EL 18 DE ENERO
    # Forzamos la fecha para que coincida exactamente con tu mercado
    fecha_objetivo = "2026-01-18"
    prob_real = 0
    try:
        r_weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 40.78, 
                "longitude": -73.97, 
                "daily": "precipitation_probability_max", 
                "timezone": "America/New_York",
                "start_date": fecha_objetivo,
                "end_date": fecha_objetivo
            }
        )
        prob_real = r_weather.json()['daily']['precipitation_probability_max'][0]
        print(f"🌦️ Probabilidad Satélite para el {fecha_objetivo}: {prob_real}%")
    except:
        print("❌ Error obteniendo clima")

    # 2. PRECIO EN POLYMARKET (Búsqueda Directa por ID/Slug)
    # Usamos el nombre exacto que venía en tu link
    slug_mercado = "will-it-rain-in-nyc-on-january-18"
    precio_mercado = 0
    
    try:
        url = f"https://gamma-api.polymarket.com/events?slug={slug_mercado}"
        r_poly = requests.get(url)
        data = r_poly.json()
        
        if data:
            evento = data[0]
            titulo = evento.get('title')
            markets = evento.get('markets', [])
            if markets:
                # Extraemos el precio del 'YES'
                prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                precio_mercado = float(prices[0]) * 100
                print(f"📊 Mercado Encontrado: {titulo}")
                print(f"💰 Precio actual del 'YES': {precio_mercado}%")
        else:
            print(f"⚠️ No encontré el mercado con el nombre: {slug_mercado}")

    except Exception as e:
        print(f"❌ Error API Polymarket: {e}")

    # 3. ANÁLISIS DE RENTABILIDAD
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "========================================")
        print(f"🔍 VENTAJA DETECTADA (EDGE): {ventaja:.2f}%")
        
        if ventaja > 10:
            print("💰 ACCIÓN: COMPRARÍA 'YES'")
            print(f"Razón: La ciencia ({prob_real}%) es muy superior al precio ({precio_mercado}%)")
        elif ventaja < -10:
            print("📉 ACCIÓN: NO COMPRARÍA")
            print("Razón: El mercado está pagando demasiado para un riesgo alto.")
        else:
            print("⚖️ ACCIÓN: ESPERAR")
            print("Razón: El precio es justo según los satélites.")
        print("========================================\n")

if __name__ == "__main__":
    run_simulation()
