import requests
import json
from datetime import datetime

def run_bot():
    print("--- 🎯 BUSCANDO MERCADO DE LLUVIA (MODO AGRESIVO) ---")
    
    # Vamos a probar palabras clave específicas de los mercados de clima
    palabras_clave = ["Rain NYC", "Precipitation", "Central Park"]
    encontrado = False

    for busqueda in palabras_clave:
        print(f"\n🔎 Probando búsqueda: '{busqueda}'...")
        
        try:
            url = "https://gamma-api.polymarket.com/events"
            # Limit 20 es suficiente si la búsqueda es precisa
            r = requests.get(url, params={"q": busqueda, "closed": "false", "limit": 20})
            events = r.json()
            
            for event in events:
                title = event.get('title', '')
                
                # Filtramos: Solo imprimimos si parece de clima
                if "Rain" in title or "Precipitation" in title or "inches" in title:
                    print(f"✅ ¡ENCONTRADO!: 👉 {title}")
                    encontrado = True
                    
        except Exception as e:
            print(f"❌ Error conectando: {e}")

    if not encontrado:
        print("\n⚠️ Sigue sin salir. Es posible que hoy no hayan abierto el mercado todavía.")
        print("Intenta buscar manualmente en polymarket.com 'Rain NYC' para ver si existe.")

if __name__ == "__main__":
    run_bot()
