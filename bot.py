import requests
import json
import re
import os
from datetime import datetime

# === CONFIGURACIÓN DE COSTOS REALES ===
CAPITAL_TOTAL = 50.0 
POLYMARKET_FEE = 0.002  # 0.2% de comisión por transacción
GAS_ESTIMADO = 0.01     # Costo fijo en USDC por el gas de Polygon
SLIPPAGE_BUFFER = 0.01  # Margen de seguridad del 1% para el precio
UMBRAL_VENTAJA_MINIMA = 12.0 # Ventaja neta después de costos

class CryptoWeatherBotPro:
    def __init__(self):
        self.ciudades = {
            "seoul": [37.56, 126.97, "celsius"],
            "atlanta": [33.74, -84.38, "fahrenheit"],
            "nyc": [40.71, -74.00, "fahrenheit"]
        }

    def calcular_beneficio_real(self, precio_mercado, monto_invertir):
        """
        Calcula cuánto dinero queda realmente después de pagar comisiones y gas.
        """
        # Costo de la comisión de la plataforma
        costo_fee = monto_invertir * POLYMARKET_FEE
        # Costo total de entrada
        inversion_total = monto_invertir + costo_fee + GAS_ESTIMADO
        
        # El precio real de compra sube debido al slippage
        precio_con_slippage = precio_mercado * (1 + SLIPPAGE_BUFFER)
        
        return inversion_total, precio_con_slippage

    def run_trading_logic(self):
        print(f"--- 🛡️ GESTIÓN DE COSTOS ACTIVADA: {datetime.now()} ---")
        
        # ... (Lógica de escaneo y clima igual a la anterior)
        # Ejemplo con datos de Seúl:
        prob_real = 48.0 # Supongamos 48% de confianza del satélite
        precio_pantalla = 16.0 # 16% o 0.16 USDC
        
        # 1. AJUSTE DE PRECIO POR COSTOS
        monto_sugerido = 5.0 # Ejemplo de inversión de 5 USDC
        costo_total, precio_real = self.calcular_beneficio_real(precio_pantalla, monto_sugerido)
        
        # 2. VENTAJA NETA (EDGE REAL)
        # La ventaja ahora se calcula sobre el precio que realmente vas a pagar
        ventaja_neta = prob_real - precio_real
        
        print(f"📊 Análisis de Costos:")
        print(f"   Precio en web: {precio_pantalla}%")
        print(f"   Precio Real (inc. Fees + Slippage): {precio_real:.2f}%")
        print(f"   Costo total de operación (inc. Gas): ${costo_total:.3f} USDC")
        
        if ventaja_neta >= UMBRAL_VENTAJA_MINIMA:
            # Cálculo de ganancia potencial neta
            ganancia_bruta = (monto_sugerido / (precio_real/100)) - monto_sugerido
            ganancia_neta = ganancia_bruta - (costo_total - monto_sugerido)
            
            print(f"🚀 SEÑAL POSITIVA: Ventaja neta de {ventaja_neta:.2f}%")
            print(f"💰 Ganancia Neta Proyectada: ${ganancia_neta:.2f} USDC")
        else:
            print(f"⚖️ OPERACIÓN RECHAZADA: Los fees y el riesgo reducen la ventaja a {ventaja_neta:.2f}%")

if __name__ == "__main__":
    bot = CryptoWeatherBotPro()
    bot.run_trading_logic()
