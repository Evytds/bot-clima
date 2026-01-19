import requests
import json
import os
import re
import math
import csv
from datetime import datetime, timedelta

# === METADATOS DE IDENTIDAD ===
VERSION = "5.7.0-STABLE"
print(f"🚀 [INIT] WeatherTrader {VERSION} | {datetime.now().strftime('%H:%M:%S')}")

# === CONFIGURACIÓN INSTITUCIONAL ===
CAPITAL_INICIAL = 196.70  
BASE_SIGMA = 1.3          
EDGE_THRESHOLD = 0.07     
MAX_EVENT_EXPOSURE = 0.03 
MAX_CLUSTER_EXPOSURE = 0.08 
KELLY_FRACTION = 0.25     
COMISION_GANANCIA = 0.02  

POLY_URL = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket"

class WeatherTraderV5_7:
    def __init__(self):
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

    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json", 'r') as f:
                    d = json.load(f)
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

    def safe_price(self, outcome):
        try:
            p = outcome.get("price")
            return float(p) if p and float(p) > 0 else None
        except: return None

    def resolver_mercados_pendientes(self):
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        pendientes_actualizados = {}
        for m_id, m in self.pendientes.items():
            if m.get('fecha_expiracion', '9999-12-31') < hoy_str:
                t_real = self.obtener_clima_historico(m['lat'], m['lon'], m['fecha_expiracion'])
                if t_real is not None:
                    exito = (t_real > m['umbral']) if m['op'] == ">" else (t_real < m['umbral'])
                    gano = (m['lado'] == "YES" and exito) or (m['lado'] == "NO" and not exito)
                    res_dinero = m['win_neto'] if gano else -m['stake']
                    self.data["balance"] += res_dinero
                    self._registrar_en_auditoria(m, t_real, gano, res_dinero)
                else: pendientes_actualizados[m_id] = m
            else: pendientes_actualizados[m_id] = m
        self.pendientes = pendientes_actualizados

    def _registrar_en_auditoria(self, m, t_real, gano, res):
        file_exists = os.path.isfile("auditoria_detallada.csv")
        with open("auditoria_detallada.csv", 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Ciudad", "Lado", "Prob", "Precio", "Stake", "Umbral", "Op", "T_Real", "Resultado_USD", "Kelly_f"])
            writer.writerow([datetime.now(), m['ciudad'], m['lado'], f"{m['prob']:.4f}", f"{m['precio']:.4f}", f"{m['stake']:.2f}", m['umbral'], m['op'], t_real, f"{res:.2f}", f"{m.get('kelly_teorico', 0):.4f}"])

    def obtener_clima_historico(self, lat, lon, fecha):
        try:
            url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={fecha}&end_date={fecha}&daily=temperature_2m_max&timezone=auto"
            res = requests.get(url, timeout=10).json()
            return res.get('daily', {}).get('temperature_2m_max', [None])[0]
        except: return None

    def ejecutar_trade(self, ciudad, config):
        if any(m.get("ciudad") == ciudad for m in self.pendientes.values()): return
        
        total_riesgo = sum(m.get('stake', 0) for m in self.pendientes.values())
        if total_riesgo >= (self.data["balance"] * MAX_CLUSTER_EXPOSURE): return

        query = '{ markets(first: 3, where: {question_contains_nocase: "%s"}) { id question endDate outcomes { name price } volume } }' % ciudad
        try:
            response = requests.post(POLY_URL, json={"query": query}, timeout=15)
            res = response.json()

            # --- ESCUDO DEFENSIVO AVANZADO ---
            if "errors" in res or "data" not in res:
                print(f"⚠️ [API] No se recibió 'data' para {ciudad}. Respuesta completa: {res}")
                return

            data_root = res["data"]
            markets_raw = data_root.get("markets")
            if not isinstance(markets_raw, list):
                print(f"⚠️ [API] 'markets' no es una lista para {ciudad}")
                return
            # ----------------------------------

            url_f = f"https://api.open-meteo.com/v1/forecast?latitude={config['lat']}&longitude={config['lon']}&daily=temperature_2m_max&timezone=auto&forecast_days=1"
            f_res = requests.get(url_f, timeout=10).json()
            t_forecast = f_res.get('daily', {}).get('temperature_2m_max', [None])[0]
            if t_forecast is None: return

            for mkt in markets_raw:
                if float(mkt.get("volume", 0)) < 5000: continue
                
                match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)", mkt.get("question", ""), re.IGNORECASE)
                if not match: continue
                threshold = (float(match.group(1)) - 32) * 5/9 if match.group(2).lower() in ["f", "fahrenheit"] else float(match.group(1))
                op = "<" if any(w in mkt.get("question", "").lower() for w in ["below", "under", "less"]) else ">"

                outcomes = mkt.get("outcomes", [])
                p_yes = next((self.safe_price(o) for o in outcomes if o["name"].lower() == "yes" and self.safe_price(o) is not None), None)
                p_no = next((self.safe_price(o) for o in outcomes if o["name"].lower() == "no" and self.safe_price(o) is not None), None)
                if p_yes is None or p_no is None: continue

                # Modelo de Probabilidad
                z = (t_forecast - threshold) / BASE_SIGMA
                prob_gt = max(0.001, min(0.999, 0.5 * (1 + math.erf(z / math.sqrt(2)))))
                prob_yes = prob_gt if op == ">" else (1 - prob_gt)
                
                lado, prob, precio = ("YES", prob_yes, p_yes) if prob_yes > p_yes else ("NO", (1 - prob_yes), p_no)

                edge = prob - precio
                if edge > EDGE_THRESHOLD:
                    b = (1 / precio) - 1
                    kelly_f = min((b * prob - (1 - prob)) / b, 0.5) 
                    
                    if kelly_f > 0.01:
                        stake_pct = max(0, min(kelly_f * KELLY_FRACTION, MAX_EVENT_EXPOSURE))
                        stake = (self.data["balance"] - total_riesgo) * stake_pct
                        if stake < 1.0: continue
                        
                        ts_raw = mkt.get("endDate")
                        try:
                            ts = int(ts_raw) if ts_raw and str(ts_raw).isdigit() else 0
                            fecha_exp = datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts > 0 else (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                        except:
                            fecha_exp = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

                        self.pendientes[mkt["id"]] = {
                            "ciudad": ciudad, "lado": lado, "prob": prob, "precio": precio,
                            "stake": stake, "umbral": threshold, "op": op,
                            "win_neto": (stake * b) * (1 - COMISION_GANANCIA),
                            "fecha_expiracion": fecha_exp,
                            "lat": config["lat"], "lon": config["lon"],
                            "kelly_teorico": kelly_f
                        }
                        total_riesgo += stake
                        print(f"🎯 Trade Registrado: {ciudad} | Prob: {prob:.1%} | Kelly: {kelly_f:.2%}")
        except Exception as e:
            print(f"⚠️ Error Crítico en {ciudad}: {e}")

    def calcular_metricas_riesgo(self):
        if not self.data["historial"]: return
        saldos = [h["balance"] for h in self.data["historial"]]
        if len(saldos) < 2: return

        peak = saldos[0]
        max_dd = 0
        for s in saldos:
            if s > peak: peak = s
            dd = (peak - s) / peak
            if dd > max_dd: max_dd = dd

        retornos = [(saldos[i] - saldos[i-1])/saldos[i-1] for i in range(1, len(saldos))]
        mean_ret = sum(retornos) / len(retornos)
        std_dev = math.sqrt(sum((r - mean_ret)**2 for r in retornos) / len(retornos))
        sharpe = (mean_ret / std_dev * math.sqrt(17520)) if std_dev > 0 else 0

        print(f"📈 [STATS] Equity: ${self.data['balance']:.2f} | Max DD: {max_dd:.2%} | Sharpe: {sharpe:.2f}")

    def ejecutar(self):
        self.resolver_mercados_pendientes()
        ciudades = list(self.ciudades_config.items())
        import random
        random.shuffle(ciudades)
        for ciudad, config in ciudades: self.ejecutar_trade(ciudad, config)
        
        if not self.pendientes: print("ℹ️ Ciclo completado: Sin trades activos.")

        if self.data["balance"] > self.data["peak_balance"]: self.data["peak_balance"] = self.data["balance"]
        self.data["historial"].append({"fecha": datetime.now().strftime("%d/%m %H:%M"), "balance": self.data["balance"]})
        self.data["historial"] = self.data["historial"][-100:]

        with open("mercados_pendientes.json", 'w') as f: json.dump(self.pendientes, f)
        with open("billetera_virtual.json", 'w') as f: json.dump(self.data, f)
        self.calcular_metricas_riesgo()

if __name__ == "__main__":
    WeatherTraderV5_7().ejecutar()
