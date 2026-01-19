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

import matplotlib
matplotlib.use('Agg')  # Headless para servidores/VPS
import matplotlib.pyplot as plt
import numpy as np

# === METADATOS ===
VERSION = "6.5.1-QUANT_PRO+"
print(f"🚀 [INIT] WeatherTrader {VERSION} | {datetime.now().strftime('%H:%M:%S')}")

# === CONFIGURACIÓN INSTITUCIONAL ===
CAPITAL_INICIAL = 196.70
EDGE_THRESHOLD_BASE = 0.07
MAX_EVENT_EXPOSURE = 0.03
MAX_CLUSTER_EXPOSURE = 0.08
KELLY_FRACTION_BASE = 0.25
COMISION_GANANCIA = 0.02

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

class WeatherTraderV6_5_1:
    def __init__(self):
        self.session = self._configurar_sesion()
        self.data = self._cargar_datos()
        self.pendientes = self._cargar_pendientes()
        self.ciudades_config = {
            "Seoul": {"lat": 37.56, "lon": 126.97},
            "Atlanta": {"lat": 33.74, "lon": -84.38},
            "Dallas": {"lat": 32.77, "lon": -96.79},
            "Seattle": {"lat": 47.60, "lon": -122.33},
            "New York": {"lat": 40.71, "lon": -74.00},
            "London": {"lat": 51.50, "lon": -0.12}
        }
        if not os.path.exists("reports"): os.makedirs("reports")

    def _configurar_sesion(self):
        sesion = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        sesion.mount('https://', HTTPAdapter(max_retries=retries))
        return sesion

    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json",'r') as f:
                    d = json.load(f)
                    d.setdefault("peak_balance", d.get("balance", CAPITAL_INICIAL))
                    d.setdefault("historial", [])
                    return d
            except: pass
        return {"balance": CAPITAL_INICIAL, "peak_balance": CAPITAL_INICIAL, "historial": []}

    def _cargar_pendientes(self):
        if os.path.exists("mercados_pendientes.json"):
            try:
                with open("mercados_pendientes.json",'r') as f: return json.load(f)
            except: pass
        return {}

    def safe_price(self, p_raw):
        try: return float(p_raw) if p_raw and 0 < float(p_raw) < 1 else None
        except: return None

    def consultar_clima(self, url, params):
        try:
            res = self.session.get(url, params=params, timeout=20)
            res.raise_for_status()
            return res.json()
        except: return None

    def calibrar_sigma(self, lat, lon):
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {"latitude": lat, "longitude": lon, "start_date": start_date, "end_date": end_date,
                  "daily":"temperature_2m_max", "timezone":"auto"}
        res = self.consultar_clima(url, params)
        historial = res.get('daily', {}).get('temperature_2m_max', []) if res else []
        if not historial or len(historial) < 10: return 1.3
        mean = sum(historial)/len(historial)
        variance = sum((t-mean)**2 for t in historial)/len(historial)
        return max(0.6, math.sqrt(variance))

    def resolver_mercados_pendientes(self):
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        pendientes_actualizados = {}
        for m_id, m in self.pendientes.items():
            f_exp = m.get('fecha_expiracion')
            if f_exp and f_exp < hoy_str:
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {"latitude": m['lat'], "longitude": m['lon'], "start_date": f_exp,
                          "end_date": f_exp, "daily":"temperature_2m_max", "timezone":"auto"}
                res = self.consultar_clima(url, params)
                t_real = res.get('daily', {}).get('temperature_2m_max',[None])[0] if res else None
                if t_real is not None:
                    exito = (t_real > m['umbral']) if m['op'] == ">" else (t_real < m['umbral'])
                    gano = (m['lado'] == "YES" and exito) or (m['lado'] == "NO" and not exito)
                    res_dinero = m['win_neto'] if gano else -m['stake']
                    self.data["balance"] += res_dinero
                    self._registrar_auditoria(m, t_real, gano, res_dinero)
                    print(f"✅ RESOLVED: {m['ciudad']} | {f_exp} | Net: ${res_dinero:.2f}")
                else: pendientes_actualizados[m_id] = m
            else: pendientes_actualizados[m_id] = m
        self.pendientes = pendientes_actualizados

    def _registrar_auditoria(self, m, t_real, gano, res):
        file_exists = os.path.isfile("auditoria_detallada.csv")
        with open("auditoria_detallada.csv",'a',newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp","Ciudad","Lado","Prob","Precio","Stake","Umbral","Op","T_Real","Resultado_USD","Kelly_f","Sigma","Edge"])
            writer.writerow([datetime.now(), m['ciudad'], m['lado'], f"{m['prob']:.4f}", f"{m['precio']:.4f}", f"{m['stake']:.2f}", m['umbral'], m['op'], t_real, f"{res:.2f}", f"{m.get('kelly_teorico',0):.4f}", m.get('sigma_usada',1.3), m.get('edge',0)])

    def ejecutar_trade(self, ciudad, config):
        if any(m.get("ciudad")==ciudad for m in self.pendientes.values()): return
        riesgo_total = sum(m.get('stake',0) for m in self.pendientes.values())
        if riesgo_total >= (self.data["balance"]*MAX_CLUSTER_EXPOSURE): return

        try:
            params = {"active":"true","closed":"false","query":ciudad,"limit":25}
            res_gamma = self.session.get(GAMMA_API_URL, params=params, timeout=20).json()
            if not isinstance(res_gamma,list): return

            res_f = self.consultar_clima("https://api.open-meteo.com/v1/forecast",
                        {"latitude":config['lat'],"longitude":config['lon'],
                         "daily":"temperature_2m_max","timezone":"auto","forecast_days":1})
            t_forecast = res_f.get('daily',{}).get('temperature_2m_max',[None])[0] if res_f else None
            if t_forecast is None: return

            sigma = self.calibrar_sigma(config['lat'], config['lon'])
            edge_threshold = EDGE_THRESHOLD_BASE * (1 + 0.5 * (sigma - 1.3))
            kelly_fraction = KELLY_FRACTION_BASE * (1.3 / sigma)

            for mkt in res_gamma:
                pregunta = mkt.get("question", "").lower()
                if not any(k in pregunta for k in ["temperature", "degrees", "°", "high"]): continue
                if float(mkt.get("liquidity", 0)) < 1000: continue

                match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", pregunta)
                if not match: continue
                threshold = float(match.group(1))
                if match.group(2) in ["f", "fahrenheit"]: threshold = (threshold - 32) * 5/9
                op = "<" if any(w in pregunta for w in ["below", "under", "less"]) else ">"

                try:
                    outcomes = json.loads(mkt.get("outcomes", "[]"))
                    prices = json.loads(mkt.get("outcomePrices", "[]"))
                    mapping = dict(zip([o.lower() for o in outcomes], prices))
                    p_yes, p_no = self.safe_price(mapping.get("yes")), self.safe_price(mapping.get("no"))
                    if p_yes is None or p_no is None: continue
                except: continue

                z = (t_forecast - threshold) / sigma
                prob_gt = max(0.001, min(0.999, 0.5 * (1 + math.erf(z / math.sqrt(2)))))
                prob_yes = prob_gt if op == ">" else 1 - prob_gt
                lado, prob, precio = ("YES", prob_yes, p_yes) if prob_yes > p_yes else ("NO", 1 - prob_yes, p_no)
                edge = prob - precio

                if edge > edge_threshold:
                    b = (1 / precio) - 1
                    kelly_f = min((b * prob - (1 - prob)) / b, 0.5) * kelly_fraction
                    if kelly_f > 0.01:
                        stake_pct = min(kelly_f, MAX_EVENT_EXPOSURE)
                        stake = (self.data["balance"] - riesgo_total) * stake_pct
                        if stake < 1.0: continue
                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": round(prob, 4), "precio": precio,
                            "stake": round(stake, 2), "umbral": threshold, "op": op,
                            "win_neto": round((stake * b) * (1 - COMISION_GANANCIA), 2),
                            "fecha_expiracion": mkt.get("endDate", "").split("T")[0],
                            "lat": config["lat"], "lon": config["lon"], "sigma_usada": round(sigma, 2),
                            "edge": round(edge, 4)
                        }
                        riesgo_total += stake
                        print(f"🎯 TRADE: {ciudad} | {lado} | Edge: {edge:.2%}")
        except Exception as e: print(f"⚠️ Error {ciudad}: {e}")

    def generar_reporte_grafico(self):
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            hist = [h['balance'] for h in self.data['historial']]
            if len(hist) < 2: return

            equity = np.array(hist)
            peak = np.maximum.accumulate(equity)
            drawdown = equity - peak
            
            # Sharpe Anualizado (aprox 24 ejecuciones/día)
            returns = np.diff(equity) / equity[:-1]
            sharpe = (np.mean(returns) / np.std(returns)) * math.sqrt(252 * 24) if np.std(returns) > 0 else 0

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
            
            ax1.plot(equity, color='#2ecc71', linewidth=2, label="Equity")
            ax1.set_title(f"Performance Report | Balance: ${equity[-1]:.2f} | Sharpe: {sharpe:.2f}")
            ax1.grid(True, alpha=0.3)
            ax1.legend()

            ax2.fill_between(range(len(drawdown)), drawdown, 0, color='#e74c3c', alpha=0.3, label="Drawdown")
            ax2.set_ylabel("Drawdown USD")
            ax2.grid(True, alpha=0.3)
            ax2.legend()

            plt.tight_layout()
            plt.savefig(f"reports/perf_{ts}.png")
            plt.close()
            print(f"📊 Reporte analítico generado en /reports/ ({ts})")
        except Exception as e: print(f"⚠️ Error en reporte: {e}")

    def ejecutar(self):
        self.resolver_mercados_pendientes()
        for ciudad, config in self.ciudades_config.items():
            self.ejecutar_trade(ciudad, config)

        self.data["historial"].append({"fecha": datetime.now().strftime("%d/%m %H:%M"), "balance": round(self.data["balance"], 2)})
        if self.data["balance"] > self.data["peak_balance"]: self.data["peak_balance"] = self.data["balance"]

        with open("mercados_pendientes.json", "w") as f: json.dump(self.pendientes, f, indent=2)
        with open("billetera_virtual.json", "w") as f: json.dump(self.data, f, indent=2)
        
        self.generar_reporte_grafico()
        print(f"📈 [FINAL] Balance: ${self.data['balance']:.2f} | Activos: {len(self.pendientes)}")

if __name__ == "__main__":
    WeatherTraderV6_5_1().ejecutar()
