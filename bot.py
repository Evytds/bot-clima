import requests
import json
from datetime import datetime

def run_simulation():
    print(f"--- 🚀 BOT ANALISTA (TIRO AL BLANCO): {datetime.now()} ---")
    
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
        print("❌ Error clima")

    # 2. CONEXIÓN DIRECTA AL MERCADO
    # Este 'slug' es el nombre técnico que Polymarket usa en su base de datos
    slug_directo = "will-it-rain-in-nyc-on-january-18"
    precio_mercado = 0
    
    try:
        # Consultamos directamente por el identificador del mercado
        url = f"https://gamma-api.polymarket.com/events?slug={slug_directo}"
        r = requests.get(url)
        data = r.json()
        
        if data and len(data) > 0:
            titulo = data[0].get('title')
            markets = data[0].get('markets', [])
            if markets:
                prices = json.loads(markets[0].get('outcomePrices', '["0", "0"]'))
                precio_mercado = float(prices[0]) * 100
                print(f"✅ MERCADO ENCONTRADO: {titulo}")
                print(f"💰 Precio actual del 'YES': {precio_mercado}%")
        else:
            print(f"⚠️ La API aún no reconoce el mercado: {slug_directo}")
            print("💡 Intentando búsqueda alternativa por palabras clave...")
            # Búsqueda de respaldo
            r_alt = requests.get("https://gamma-api.polymarket.com/events?q=NYC%20Rain&active=true")
            for e in r_alt.json():
                if "Jan 18" in e.get('title', ''):
                    prices = json.loads(e['markets'][0]['outcomePrices'])
                    precio_mercado = float(prices[0]) * 100
                    print(f"✅ ENCONTRADO EN BÚSQUEDA: {e['title']} | Precio: {precio_mercado}%")
                    break

    except Exception as err:
        print(f"❌ Error en la conexión: {err}")

    # 3. ANÁLISIS DE RENTABILIDAD
    if prob_real > 0 and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"🔍 VENTAJA DETECTADA (EDGE): {ventaja:.2f}%")
        
        if ventaja > 10:
            print("💰 ACCIÓN: COMPRARÍA 'YES'")
            print(f"Justificación: La ciencia ({prob_real}%) es muy superior al precio ({precio_mercado}%)")
        elif ventaja < -10:
            print("📉 ACCIÓN: NO COMPRARÍA")
            print("Justificación: El mercado está pagando demasiado para el riesgo.")
        else:
            print("⚖️ ACCIÓN: ESPERAR")
            print("Justificación: El precio es justo según los satélites.")
        print("="*40 + "\n")
    else:
        print("\n⚠️ Aún no podemos calcular la ventaja. Reintenta en unos minutos.")

if __name__ == "__main__":
    run_simulation()
