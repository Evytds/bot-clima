import requests
import json
from datetime import datetime

def run_bot():
    print(f"--- 🕵️ BUSCANDO NOMBRES DE MERCADOS ---")
    
    # Buscamos la palabra "Rain" en general
    try:
        url = "https://gamma-api.polymarket.com/events"
        # Traemos 50 resultados para encontrar el de NY seguro
        r = requests.get(url, params={"q": "Rain", "closed": "false", "limit": 50})
        events = r.json()
        
        print(f"✅ Se encontraron {len(events)} eventos. MIRA ESTA LISTA:")
        print("="*50)
        
        for event in events:
            title = event.get('title', 'Sin título')
            # Imprimimos el título para que tú lo leas
            print(f"👉 {title}")
            
        print("="*50)
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_bot()
