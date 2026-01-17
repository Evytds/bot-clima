import requests
import json
from datetime import datetime

def run_bot():
    print(f"--- 🕵️ BUSCANDO MERCADOS: {datetime.now()} ---")
    
    # 1. Buscar mercados generales de "Rain" o "New York"
    try:
        # Buscamos 'Rain' para ver qué sale
        r = requests.get("https://gamma-api.polymarket.com/events", params={"q": "Rain", "closed": "false", "limit": 20})
        events = r.json()
        
        print(f"✅ Se encontraron {len(events)} eventos posibles. LISTA DE NOMBRES:")
        print("="*40)
        
        for event in events:
            title = event.get('title', 'Sin título')
            print(f"👉 {title}")
            
        print("="*40)
        
    except Exception as e:
        print(f"❌ Error buscando en Polymarket: {e}")

if __name__ == "__main__":
    run_bot()
