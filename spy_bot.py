import requests
import pandas as pd
from datetime import datetime

# TU OBJETIVO
TARGET_WALLET = "0x9D3E989DD42030664e6157DAE42f6d549542C49E"

def analyze_wallet(address):
    print(f"🕵️ Analizando operativa de: {address}")
    
    # Endpoint de Data-API de Polymarket (Público)
    url = f"https://data-api.polymarket.com/activity?user={address}&limit=100&sortBy=timestamp&sortDirection=DESC"
    
    try:
        r = requests.get(url).json()
    except Exception as e:
        print("Error conectando a API:", e)
        return

    if not r:
        print("❌ No se encontraron datos recientes o la wallet es nueva.")
        return

    data = []
    for item in r:
        # Extraemos datos clave
        action = item.get("type") # ORDER, TRADE, LIQUIDITY
        market = item.get("marketSlug", "Unknown")
        side = item.get("outcome", "N/A")
        size = float(item.get("size", 0))
        price = float(item.get("price", 0))
        timestamp = int(item.get("timestamp", 0))
        
        # Convertir fecha
        dt = datetime.fromtimestamp(timestamp/1000)
        
        data.append({
            "Date": dt,
            "Market": market,
            "Action": action,
            "Side": side,
            "Price": price,
            "Size": size,
            "Value": size * price
        })

    df = pd.DataFrame(data)
    
    if df.empty:
        print("Sin operaciones legibles.")
        return

    # --- ANÁLISIS DE ESTRATEGIA ---
    print("\n📊 REPORTE DE INTELIGENCIA")
    print("-" * 30)
    
    # 1. ¿Qué mercados opera más?
    top_markets = df['Market'].value_counts().head(3)
    print(f"🏆 Top 3 Mercados:\n{top_markets}")
    
    # 2. ¿Tamaño promedio de apuesta?
    avg_bet = df['Value'].mean()
    print(f"\n💰 Tamaño promedio de orden: ${avg_bet:.2f}")
    
    # 3. ¿Es Sniper o Trader casual?
    # Calculamos tiempo entre operaciones
    df['TimeDiff'] = df['Date'].diff().dt.total_seconds().abs()
    avg_speed = df['TimeDiff'].mean()
    print(f"\n⚡ Velocidad (segundos entre trades): {avg_speed:.1f}s")
    
    if avg_speed < 10:
        print("   >> ALERTA: Probablemente es un BOT de Alta Frecuencia (HFT/MM)")
    elif avg_speed < 300:
        print("   >> ALERTA: Trader activo / Scalper")
    else:
        print("   >> Trader posicional (Humano)")

    # 4. Ver últimas 5 jugadas
    print("\n📜 Últimas 5 operaciones:")
    print(df[['Date', 'Market', 'Side', 'Price', 'Value']].head(5).to_string(index=False))

if __name__ == "__main__":
    analyze_wallet(TARGET_WALLET)
