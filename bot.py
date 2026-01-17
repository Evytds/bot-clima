import requests
import json
from datetime import datetime

def run_bot():
    print("--- 🕵️ INICIANDO MODO DETECTIVE ---")
    
    # Buscamos mercados que digan "Rain"
    try:
        url = "https://gamma-api.polymarket.com/events"
        # Pedimos 50 resultados para encontrar el de NY sí o sí
        r = requests.get(url, params={"q": "Rain", "closed": "false", "limit": 50})
        events = r.json()
        
        print(f"✅ ENCONTRÉ {len(events)} MERCADOS. COPIA EL NOMBRE CORRECTO DE AQUÍ ABAJO:")
        print("👇" * 20)
        
        for event in events:
            title = event.get('title', 'Sin título')
            print(f"👉 {title}")
            
        print("👆" * 20)
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_bot()
