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
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

VERSION = "6.5.2-QUANT_PRO+_LOOP"
print(f"🚀 [INIT] WeatherTrader {VERSION} | {datetime.now().strftime('%H:%M:%S')}")

# ===== CONFIGURACIÓN =====
CAPITAL_INICIAL = 196.70
EDGE_THRESHOLD_BASE = 0.07
MAX_EVENT_EXPOSURE = 0.03
MAX_CLUSTER_EXPOSURE = 0.08
KELLY_FRACTION_BASE = 0.25
COMISION_GANANCIA = 0.02
GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"
LOOP_INTERVAL = 600  # 10 minutos entre ciclos

class WeatherTraderLoop:
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
        if not os.path.exists("reports"):
            os.makedirs("reports")

    # ======= Sesión HTTP con reintentos =======
    def _configurar_sesion(self):
        sesion = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504], raise_on_status=False)
        sesion.mount('https://', HTTPAdapter(max_retries=retries))
        return sesion

    # ======= Carga de datos =======
    def _cargar_datos(self):
        if os.path.exists("billetera_virtual.json"):
            try:
                with open("billetera_virtual.json",'r') as f:
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
                with open("mercados_pendientes.json",'r') as f: return json.load(f)
            except: pass
        return {}

    def safe_price(self,p_raw):
        try: return float(p_raw) if p_raw and 0<float(p_raw)<1 else None
        except: return None

    def consultar_clima(self,url,params):
        try:
            res = self.session.get(url, params=params, timeout=20)
            res.raise_for_status()
            return res.json()
        except: return None

    # ======= Sigma =======
    def calibrar_sigma(self,lat,lon):
        end_date = (datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (datetime.now()-timedelta(days=31)).strftime('%Y-%m-%d')
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {"latitude":lat,"longitude":lon,"start_date":start_date,"end_date":end_date,
                  "daily":"temperature_2m_max","timezone":"auto"}
        res = self.consultar_clima(url,params)
        historial = res.get('daily',{}).get('temperature_2m_max',[]) if res else []
        if not historial or len(historial)<10: return 1.3
        mean = sum(historial)/len(historial)
        variance = sum((t-mean)**2 for t in historial)/len(historial)
        return max(0.6, math.sqrt(variance))

    # ======= Resolver mercados pendientes =======
    def resolver_mercados_pendientes(self):
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        pendientes_actualizados = {}
        for m_id, m in self.pendientes.items():
            f_exp = m.get('fecha_expiracion')
            if f_exp and f_exp<hoy_str:
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {"latitude": m['lat'], "longitude": m['lon'], "start_date": f_exp, "end_date": f_exp,
                          "daily":"temperature_2m_max","timezone":"auto"}
                res = self.consultar_clima(url,params)
                t_real = res.get('daily',{}).get('temperature_2m_max',[None])[0] if res else None
                if t_real is not None:
                    exito = (t_real>m['umbral']) if m['op']==">" else (t_real<m['umbral'])
                    gano = (m['lado']=="YES" and exito) or (m['lado']=="NO" and not exito)
                    res_dinero = m['win_neto'] if gano else -m['stake']
                    self.data["balance"] += res_dinero
                    print(f"✅ RESOLVED: {m['ciudad']} | {f_exp} | Net: ${res_dinero:.2f}")
                else: pendientes_actualizados[m_id]=m
            else: pendientes_actualizados[m_id]=m
        self.pendientes = pendientes_actualizados

    # ======= Ejecutar trades =======
    def ejecutar_trade(self, ciudad, config):
        if any(m.get("ciudad")==ciudad for m in self.pendientes.values()): return
        riesgo_total = sum(m.get('stake',0) for m in self.pendientes.values())
        if riesgo_total >= self.data["balance"]*MAX_CLUSTER_EXPOSURE: return

        try:
            params = {"active":"true","closed":"false","query":ciudad,"limit":25}
            res_gamma = self.session.get(GAMMA_API_URL,params=params,timeout=20).json()
            if not isinstance(res_gamma,list): return

            res_f = self.consultar_clima("https://api.open-meteo.com/v1/forecast",
                                         {"latitude":config['lat'],"longitude":config['lon'],
                                          "daily":"temperature_2m_max","timezone":"auto","forecast_days":1})
            t_forecast = res_f.get('daily',{}).get('temperature_2m_max',[None])[0] if res_f else None
            if t_forecast is None: return

            sigma = self.calibrar_sigma(config['lat'],config['lon'])
            edge_threshold = EDGE_THRESHOLD_BASE*(1+0.5*(sigma-1.3))
            kelly_fraction = KELLY_FRACTION_BASE*(1.3/sigma)

            ciudad_edges=[]
            for mkt in res_gamma:
                pregunta = mkt.get("question","").lower()
                if not any(k in pregunta for k in ["temperature","degrees","°","high"]): continue
                if float(mkt.get("liquidity",0))<1000: continue

                match = re.search(r"([-+]?\d*\.?\d+)\s*(°|degrees|celsius|c|f|fahrenheit)",pregunta)
                if not match: continue
                threshold=float(match.group(1))
                if match.group(2) in ["f","fahrenheit"]: threshold=(threshold-32)*5/9
                op="<" if any(w in pregunta for w in ["below","under","less"]) else ">"

                try:
                    outcomes=json.loads(mkt.get("outcomes","[]"))
                    prices=json.loads(mkt.get("outcomePrices","[]"))
                    mapping=dict(zip([o.lower() for o in outcomes],prices))
                    p_yes,p_no=self.safe_price(mapping.get("yes")),self.safe_price(mapping.get("no"))
                    if p_yes is None or p_no is None: continue
                except: continue

                z=(t_forecast-threshold)/sigma
                prob_gt=max(0.001,min(0.999,0.5*(1+math.erf(z/math.sqrt(2)))))
                prob_yes=prob_gt if op==">" else 1-prob_gt
                lado,prob,precio=("YES",prob_yes,p_yes) if prob_yes>p_yes else ("NO",1-prob_yes,p_no)
                edge=prob-precio

                if edge>edge_threshold:
                    b=(1/precio)-1
                    kelly_f=min((b*prob-(1-prob))/b,0.5)*kelly_fraction
                    if kelly_f>0.01:
                        stake_pct=min(kelly_f,MAX_EVENT_EXPOSURE)
                        stake=(self.data["balance"]-riesgo_total)*stake_pct
                        if stake<1.0: continue
                        self.pendientes[mkt["id"]]={
                            "ciudad":ciudad,"lado":lado,"prob":round(prob,4),"precio":precio,
                            "stake":round(stake,2),"umbral":threshold,"op":op,
                            "win_neto":round((stake*b)*(1-COMISION_GANANCIA),2),
                            "fecha_expiracion":mkt.get("endDate","").split("T")[0],
                            "lat":config["lat"],"lon":config["lon"],
                            "sigma_usada":round(sigma,2),"edge":round(edge,4),
                            "kelly_teorico":round(kelly_f,4),
                            "pregunta":pregunta[:70],"YES":"YES","NO":"NO"
                        }
                        riesgo_total+=stake
                        ciudad_edges.append(self.pendientes[mkt["id"]])

            if ciudad_edges:
                print(f"\n📌 {ciudad} | Forecast Temp: {t_forecast:.1f}°C | Sigma: {sigma:.2f}")
                print(f"{'Pregunta':<70} {'YES':>6} {'NO':>6} {'Prob':>6} {'Edge':>6} | Barra")
                for m in ciudad_edges:
                    edge_pct = m['edge']*100
                    barra='#'*int(edge_pct*10) if edge_pct>0 else ''
                    print(f"{m['pregunta']:<70} {m['YES']:>6} {m['NO']:>6} {m['prob']:>6.2f} {edge_pct:>6.1f}% | {barra}")

        except Exception as e: print(f"⚠️ Error {ciudad}: {e}")

    # ======= Reportes =======
    def generar_reporte(self):
        timestamp=datetime.now().strftime("%Y%m%d_%H%M")
        historial=[h['balance'] for h in self.data['historial']]
        if len(historial)<2: return
        equity=np.array(historial)
        peak=np.maximum.accumulate(equity)
        drawdown=equity-peak
        returns=np.diff(equity)/(equity[:-1]+1e-6)
        sharpe=(np.mean(returns)/(np.std(returns)+1e-6))*math.sqrt(252*24)

        fig,(ax1,ax2)=plt.subplots(2,1,figsize=(12,10))
        ax1.plot(equity,color='#2ecc71',linewidth=2,label="Equity")
        ax1.set_title(f"Performance | Balance: ${equity[-1]:.2f} | Sharpe: {sharpe:.2f}")
        ax1.grid(True,alpha=0.3); ax1.legend()
        ax2.fill_between(range(len(drawdown)),drawdown,0,color='#e74c3c',alpha=0.3,label="Drawdown (USD)")
        ax2.set_ylabel("Drawdown USD"); ax2.grid(True,alpha=0.3); ax2.legend()
        plt.tight_layout()
        plt.savefig(f"reports/perf_{timestamp}.png")
        plt.close()

        edges=[m['edge'] for m in self.pendientes.values()]
        if edges:
            plt.figure(figsize=(10,5))
            plt.hist(edges,bins=10,color='#3498db',alpha=0.7)
            plt.title("Distribución de Edge en Mercados Activos")
            plt.xlabel("Edge (%)")
            plt.savefig(f"reports/edge_dist_{timestamp}.png")
            plt.close()
        print(f"📊 Reporte generado en /reports/ ({timestamp})")

    def guardar_datos(self):
        with open("mercados_pendientes.json","w") as f: json.dump(self.pendientes,f,indent=2)
        with open("billetera_virtual.json","w") as f: json.dump(self.data,f,indent=2)

    # ======= Loop infinito =======
    def loop(self):
        while True:
            print(f"\n⏱️ [Ciclo] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.resolver_mercados_pendientes()
            for ciudad,config in self.ciudades_config.items():
                self.ejecutar_trade(ciudad,config)
            self.data["historial"].append({"fecha":datetime.now().strftime("%d/%m %H:%M"),
                                           "balance":round(self.data["balance"],2)})
            if self.data["balance"]>self.data["peak_balance"]:
                self.data["peak_balance"]=self.data["balance"]
            self.generar_reporte()
            self.guardar_datos()
            print(f"📈 Equity: ${self.data['balance']:.2f} | Activos: {len(self.pendientes)}")
            time.sleep(LOOP_INTERVAL)

if __name__=="__main__":
    bot = WeatherTraderLoop()
    bot.loop()
