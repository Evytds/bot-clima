import requests
import json

def run_bot():
    print("--- 🔍 LISTA COMPLETA DE MERCADOS (COPIA EL CORRECTO) ---")
    
    try:
        # Buscamos 'Rain' y traemos TODO lo que haya (50 resultados)
        url = "https://gamma-api.polymarket.com/events"
        r = requests.get(url, params={"q": "Rain", "closed": "false", "limit": 50})
        events = r.json()
        
        for event in events:
            title = event.get('title', 'Sin título')
            # Imprimimos TODOS los nombres para ver cuál es el de NY hoy
            print(f"👉 {title}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_bot()
