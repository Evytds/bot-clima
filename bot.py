import requests
import json
import os
import re
import math
import csv
import time
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuración gráfica "Headless" (Sin ventanas emergentes para servidores/VPS)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ==========================================
#        METADATOS Y CONFIGURACIÓN
# ==========================================
VERSION = "6.5.5-SILENT_LOOP"
print(f"🚀 [INIT] WeatherTrader {VERSION} | {datetime.now().strftime('%H:%M:%S')}")

# --- GESTIÓN DE RIESGO INSTITUCIONAL ---
CAPITAL_INICIAL = 196.70        # Tu capital base
EDGE_THRESHOLD_BASE = 0.07      # Ventaja mínima del 7% para entrar
MAX_EVENT_EXPOSURE = 0.03       # Max 3% del banco en un solo evento
MAX_CLUSTER_EXPOSURE = 0.08     # Max 8% de riesgo total simultáneo
KELLY_FRACTION_BASE = 0.25      # Fracción de Kelly (Conservador)
COMISION_GANANCIA = 0.02        # 2% Fee de Polymarket
LOOP_INTERVAL = 600             # Ciclo de escaneo: 10 minutos

# --- ENDPOINTS ---
GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

class WeatherTraderSilent:
    def __init__(self):
        # Inicialización de infraestructura
        self.session = self._configurar_sesion()
        self.data = self._cargar_datos()
        self.pendientes = self._cargar_pendientes()
        
        # Coordenadas de Ciudades Estratégicas
        self.ciudades_config = {
            "Seoul": {"lat": 37.56, "lon": 126.97},
            "Atlanta": {"lat": 33.74, "lon": -84.38},
            "Dallas": {"lat": 32.77, "lon": -96.79},
            "Seattle": {"lat": 47.60, "lon": -122.33},
            "New York": {"lat": 40.71, "lon": -74.00},
            "London": {"lat": 51.50, "lon": -0.12}
        }
        
        # Crear carpeta de reportes si no existe
        if not os.path.exists("reports"):
            os.makedirs("reports")

    # ==========================================
    #       CAPA DE CONEXIÓN RESILIENTE
    # ==========================================
    def _configurar_sesion(self):
        """Configura reintentos automáticos para evitar caídas por red."""
        sesion = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        sesion.mount('https://', HTTPAdapter(max_retries=retries))
        return sesion

    # ==========================================
    #       PERSISTENCIA DE DATOS (JSON)
    # ==========================================
    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json", 'r') as f:
                    d = json.load(f)
                    d.setdefault("balance", CAPITAL_INICIAL)
                    d.setdefault("peak_balance", d.get("balance", CAPITAL_INICIAL))
                    d.setdefault("historial", [])
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def _cargar_pendientes(self):
        if os.path.exists("mercados_pendientes.json"):
            try:
                with open("mercados_pendientes.json", 'r') as f: return json.load(f)
            except: pass
        return {}

    def guardar_estado(self):
        """Escribe los datos en disco al final de cada ciclo."""
        with open("mercados_pendientes.json", "w") as f: json.dump(self.pendientes, f, indent=2)
        with open("billetera_virtual.json", "w") as f: json.dump(self.data, f, indent=2)

    def safe_price(self, p_raw):
        try: return float(p_raw) if p_raw and 0 < float(p_raw) < 1 else None
        except: return None

    # ==========================================
    #       MOTOR METEOROLÓGICO (API)
    # ==========================================
    def consultar_clima(self, url, params):
        try:
            res = self.session.get(url, params=params, timeout=20)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            # Silencioso en consola para no ensuciar, a menos que sea crítico
            return None

    def calibrar_sigma(self, lat, lon):
        """
        Calcula la volatilidad (Sigma) histórica de los últimos 30 días
        para ajustar el tamaño de la apuesta según la incertidumbre local.
        """
        end_d = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_d = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        
        res = self.consultar_clima(
            "https://archive-api.open-meteo.com/v1/archive", 
            {"latitude": lat, "longitude": lon, "start_date": start_d, "end_date": end_d, "daily": "temperature_2m_max", "timezone": "auto"}
        )
        
        hist = res.get('daily', {}).get('temperature_2m_max', []) if res else []
        
        if not hist or len(hist) < 10: return 1.3 # Sigma por defecto
        
        mean = sum(hist) / len(hist)
        variance = sum((t - mean)**2 for t in hist) / len(hist)
        # Floor de 0.6 para evitar confianza excesiva en climas muy estables
        return max(0.6, math.sqrt(variance))

    # ==========================================
    #       RESOLUCIÓN DE MERCADOS (SETTLEMENT)
    # ==========================================
    def resolver_mercados(self):
        hoy = datetime.now().strftime('%Y-%m-%d')
        pendientes_act = {}
        
        for m_id, m in self.pendientes.items():
            # Si la fecha de expiración ya pasó (es anterior a hoy)
            if m.get('fecha_expiracion') and m['fecha_expiracion'] < hoy:
                # Consultar dato real histórico
                res = self.consultar_clima(
                    "https://archive-api.open-meteo.com/v1/archive", 
                    {"latitude": m['lat'], "longitude": m['lon'], "start_date": m['fecha_expiracion'], "end_date": m['fecha_expiracion'], "daily":"temperature_2m_max", "timezone":"auto"}
                )
                t_real = res.get('daily',{}).get('temperature_2m_max',[None])[0] if res else None
                
                if t_real is not None:
                    # Determinar ganador
                    exito = (t_real > m['umbral']) if m['op'] == ">" else (t_real < m['umbral'])
                    gano = (m['lado'] == "YES" and exito) or (m['lado'] == "NO" and not exito)
                    
                    # Calcular impacto en capital
                    profit = m['win_neto'] if gano else -m['stake']
                    self.data["balance"] += profit
                    
                    print(f"💰 RESUELTO: {m['ciudad']} | Real: {t_real}°C | {'GANADO' if gano else 'PERDIDO'} | Net: ${profit:.2f}")
                else:
                    # Si Open-Meteo aún no tiene el dato, esperar al siguiente ciclo
                    pendientes_act[m_id] = m
            else:
                pendientes_act[m_id] = m
        
        self.pendientes = pendientes_act

    # ==========================================
    #       ANALÍTICA Y REPORTES
    # ==========================================
    def generar_reporte(self):
        try:
            hist = [h['balance'] for h in self.data['historial']]
            if len(hist) < 2: return
            
            equity = np.array(hist)
            peak = np.maximum.accumulate(equity)
            drawdown = equity - peak
            
            # Crear figura con 2 paneles: Equity y Drawdown
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
            
            # Panel 1: Equity
            ax1.plot(equity, color='#2ecc71', lw=2)
            ax1.set_title(f"Equity Curve | Balance: ${self.data['balance']:.2f}")
            ax1.grid(True, alpha=0.3)
            
            # Panel 2: Drawdown
            ax2.fill_between(range(len(drawdown)), drawdown, 0, color='#e74c3c', alpha=0.3)
            ax2.set_ylabel("Drawdown ($)")
            ax2.grid(True, alpha=0.3)
            
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            plt.tight_layout()
            plt.savefig(f"reports/status_{ts}.png")
            plt.close() # Libera memoria RAM
            
            # Mantenimiento: Borrar reportes viejos (mantener solo los últimos 5)
            files = sorted([os.path.join("reports", f) for f in os.listdir("reports") if f.endswith(".png")])
            if len(files) > 5:
                os.remove(files[0])
                
        except Exception as e: 
            print(f"⚠️ Error generando reporte visual: {e}")

    # ==========================================
    #       NÚCLEO DE TRADING (SCANNER)
    # ==========================================
    def escanear_mercado(self, ciudad, config):
        # Filtros de seguridad iniciales
        if any(m.get("ciudad") == ciudad for m in self.pendientes.values()): return # Ya tenemos posición en esta ciudad
        riesgo_actual = sum(m['stake'] for m in self.pendientes.values())
        if riesgo_actual >= self.data["balance"] * MAX_CLUSTER_EXPOSURE: return # Límite de riesgo global alcanzado

        try:
            # 1. Obtener Mercados de Polymarket (Gamma API)
            params = {"active":"true","closed":"false","query":ciudad,"limit":15}
            res_gamma = self.session.get(GAMMA_API_URL, params=params, timeout=20).json()
            if not isinstance(res_gamma, list): return

            # 2. Obtener Pronóstico y Volatilidad Local
            res_f = self.consultar_clima(
                "https://api.open-meteo.com/v1/forecast", 
                {"latitude":config['lat'],"longitude":config['lon'], "daily":"temperature_2m_max","timezone":"auto","forecast_days":1}
            )
            t_forecast = res_f.get('daily',{}).get('temperature_2m_max',[None])[0]
            if t_forecast is None: return
            
            sigma = self.calibrar_sigma(config['lat'], config['lon'])

            # 3. Analizar Oportunidades Matemáticas
            for mkt in res_gamma:
                # Filtro de liquidez
                if float(mkt.get("liquidity", 0)) < 1000: continue
                
                # Parsing de la pregunta
                pregunta = mkt.get("question", "").lower()
                match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", pregunta)
                if not match: continue
                
                threshold = float(match.group(1))
                if match.group(2) in ["f", "fahrenheit"]: 
                    threshold = (threshold - 32) * 5/9
                
                op = "<" if any(w in pregunta for w in ["below", "under", "less"]) else ">"

                # Obtener Precios
                try:
                    outcomes = json.loads(mkt.get("outcomes", "[]"))
                    prices = json.loads(mkt.get("outcomePrices", "[]"))
                    mapping = dict(zip([o.lower() for o in outcomes], prices))
                    p_yes = self.safe_price(mapping.get("yes"))
                    p_no = self.safe_price(mapping.get("no"))
                    if not p_yes or not p_no: continue
                except: continue

                # Cálculo de Probabilidad (Gaussiana)
                z = (t_forecast - threshold) / sigma
                prob_gt = max(0.001, min(0.999, 0.5 * (1 + math.erf(z / math.sqrt(2)))))
                prob_yes = prob_gt if op == ">" else 1 - prob_gt
                
                # Identificar lado con valor
                lado, prob, precio = ("YES", prob_yes, p_yes) if prob_yes > p_yes else ("NO", 1 - prob_yes, p_no)
                edge = prob - precio

                # Ejecución (Criterio de Kelly)
                if edge > EDGE_THRESHOLD_BASE: # Solo si Edge > 7%
                    b = (1 / precio) - 1
                    kelly = min((b * prob - (1 - prob)) / b, 0.5) * KELLY_FRACTION_BASE * (1.3/sigma)
                    
                    if kelly > 0.01: # Solo si la apuesta sugerida es > 1% del banco
                        stake = (self.data["balance"] - riesgo_actual) * min(kelly, MAX_EVENT_EXPOSURE)
                        if stake < 1.0: continue

                        # Registrar Trade
                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": round(prob, 4), "precio": precio,
                            "stake": round(stake, 2), "umbral": threshold, "op": op,
                            "win_neto": round((stake * b) * (1 - COMISION_GANANCIA), 2),
                            "fecha_expiracion": mkt.get("endDate", "").split("T")[0],
                            "lat": config["lat"], "lon": config["lon"], "sigma": round(sigma, 2)
                        }
                        riesgo_actual += stake
                        print(f"🎯 TRADE: {ciudad} | {lado} | Edge: {edge:.1%} | Stake: ${stake:.2f}")

        except Exception as e: 
            # Error silencioso en el log
            print(f"⚠️ Error escaneando {ciudad}: {e}")

    # ==========================================
    #       BUCLE INFINITO PRINCIPAL
    # ==========================================
    def iniciar(self):
        print(f"⏱️ Iniciando vigilancia continua (Intervalo: {LOOP_INTERVAL}s)")
        print(f"📂 Los reportes gráficos se guardarán en la carpeta /reports")
        print(f"💵 Capital Inicial: ${self.data['balance']:.2f}")
        
        while True:
            # Timestamp en consola para saber que sigue vivo
            ts = datetime.now().strftime('%H:%M')
            print(f"\n🔄 [Ciclo {ts}] Balance: ${self.data['balance']:.2f} | Activos: {len(self.pendientes)}")
            
            # 1. Resolver apuestas pasadas
            self.resolver_mercados()
            
            # 2. Buscar nuevas oportunidades
            for ciudad, config in self.ciudades_config.items():
                self.escanear_mercado(ciudad, config)
            
            # 3. Registrar historia
            self.data["historial"].append({
                "fecha": datetime.now().strftime("%d/%m %H:%M"), 
                "balance": self.data["balance"]
            })
            
            # 4. Actualizar Peak Balance (para Drawdown)
            if self.data["balance"] > self.data["peak_balance"]:
                self.data["peak_balance"] = self.data["balance"]
            
            # 5. Generar Reportes y Guardar
            self.generar_reporte()
            self.guardar_estado()
            
            # 6. Esperar al siguiente ciclo
            time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    WeatherTraderSilent().iniciar()
