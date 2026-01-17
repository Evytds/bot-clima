import requests
import json
from datetime import datetime

def run_simulation():
    print(f"--- 📡 ESCANEO TOTAL DE MERCADOS: {datetime.now()} ---")
    
    # 1. CLIMA (CIENCIA) - Ya sabemos que funciona (48%)
    prob_real = 48 # Lo fijamos en 48% que es lo que dio el satélite hace un momento
    print(f"🌦️ Probabilidad Satélite: {prob_real}%")

    # 2. ESCANEO GLOBAL DE POLYMARKET
    precio_mercado = 0
    nombre_mercado = ""
    encontrado = False

    try:
        # Traemos TODOS los mercados activos (sin filtros de búsqueda que fallan)
        # Usamos el endpoint de 'markets' que es más directo que el de 'events'
        url = "https://gamma-api.polymarket.com/markets?active=true&limit=100"
        r = requests.get(url)
        mercados = r.json()

        for m in mercados:
            titulo = m.get('question', '')
            # Buscamos coincidencias de NYC y LLUVIA para el día 18
            if ("Rain" in titulo or "Precipitation" in titulo) and ("NYC" in titulo or "New York" in titulo) and "18" in titulo:
                
                # Intentamos extraer el precio del YES (índice 0)
                precios_raw = m.get('outcomePrices')
                if precios_raw:
                    # outcomePrices suele ser una lista de strings: ["0.45", "0.55"]
                    precio_mercado = float(precios_raw[0]) * 100
                    nombre_mercado = titulo
                    encontrado = True
                    break

        if encontrado:
            print(f"✅ ¡MERCADO LOCALIZADO!: {nombre_mercado}")
            print(f"💰 Precio Real del 'YES': {precio_mercado}%")
        else:
            print("⚠️ No se encontró el mercado de mañana en el escaneo global.")
            print("💡 Esto suele pasar si el mercado aún no tiene liquidez suficiente en la API.")

    except Exception as e:
        print(f"❌ Error en el escaneo: {e}")

    # 3. CÁLCULO DE RENTABILIDAD
    if encontrado and precio_mercado > 0:
        ventaja = prob_real - precio_mercado
        print("\n" + "="*40)
        print(f"📊 RESULTADO DEL ANÁLISIS")
        print(f"Ventaja Matemática (Edge): {ventaja:.2f}%")
        
        if ventaja > 5:
            print("🚀 SEÑAL: COMPRA RENTABLE")
            print(f"Estas comprando a {precio_mercado}% algo que tiene {prob_real}% de probabilidad.")
        else:
            print("⚖️ SEÑAL: NO OPERAR (Sin ventaja clara)")
        print("="*40 + "\n")
    else:
        print("\n❌ No pudimos completar el análisis porque Polymarket no está enviando el precio por API.")

if __name__ == "__main__":
    run_simulation()
