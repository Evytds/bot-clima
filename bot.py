import requests
import pandas as pd
from datetime import datetime

# LA WALLET QUE QUIERES ESPIAR
TARGET = "0x9D3E989DD42030664e6157DAE42f6d549542C49E"

def spy_on_wallet():
    print(f"🕵️ INVESTIGANDO A: {TARGET}")
    
    # API de Data de Polymarket
    url = f"https://data-api.polymarket.com/activity?user={TARGET}&limit=50&sortBy=timestamp&sortDirection=DESC"
    
    try:
        r = requests.get(url).json()
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return

    if not r:
        print("❌ La wallet no tiene actividad reciente o API falló.")
        return

    print(f"✅ Se encontraron {len(r)} operaciones recientes.\n")
    
    data = []
    for item in r:
        ts = int(item.get("timestamp", 0)) / 1000
        date = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        market = item.get("marketSlug", "Desconocido")
        action = item.get("type") # ORDER o TRADE
        side = item.get("outcome")
        size = float(item.get("size", 0))
        price = float(item.get("price", 0))
        
        data.append({"Fecha": date, "Mercado": market, "Acción": action, "Lado": side, "Precio": price, "Tamaño": size})

    # Convertir a DataFrame para ver fácil
    df = pd.DataFrame(data)
    
    # MOSTRAR EL REPORTE
    pd.set_option('display.max_colwidth', 50)
    print(df[["Fecha", "Mercado", "Lado", "Precio", "Tamaño"]].head(10))
    
    print("\n--- RESUMEN DE ESTRATEGIA ---")
    promedio = df["Tamaño"].mean()
    print(f"💰 Apuesta Promedio: ${promedio:.2f}")
    
    mercados_top = df["Mercado"].value_counts().head(3)
    print(f"🏆 Mercados Favoritos:\n{mercados_top}")

if __name__ == "__main__":
    spy_on_wallet()
