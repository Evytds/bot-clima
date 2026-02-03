# Bot autónomo para mercados de clima (Polymarket)

Este proyecto incluye un bot que escanea mercados de clima en Polymarket, agrega pronósticos de múltiples fuentes y calcula si existe una ventaja (edge) para decidir operaciones en modo **paper trading**.

## Requisitos

* Python 3.10+
* API keys de al menos un proveedor de clima:
  * `TOMORROWIO_API_KEY`
  * `WEATHERBIT_API_KEY`
  * `OPENWEATHER_API_KEY`

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración

1. Copia el archivo de ejemplo de variables de entorno:

```bash
cp .env.example .env
```

2. Completa al menos una API key en `.env`.
3. Ajusta los parámetros del bot en `config/polymarket_auto.json`.

## Uso

### Modo autónomo (paper trading)

```bash
export TOMORROWIO_API_KEY="tu_api_key"
python polymarket_bot.py --mode auto
```

El bot:

1. Escanea mercados de clima en Polymarket.
2. Filtra por odds (0.1¢ a 10¢) y liquidez mínima.
3. Consulta forecasts de varias fuentes (Tomorrow.io, Weatherbit, OpenWeather).
4. Calcula la probabilidad justa por outcome usando una normal centrada en la temperatura máxima (forecast high).
   - El bot asume bins de ~1°F al convertir rangos a probabilidades.
5. Calcula edge y EV, y registra decisiones en modo simulación.

Las decisiones quedan en `state/polymarket_auto_state.json`.

### Modo reporte (actividad de wallet)

```bash
python polymarket_bot.py --mode report --wallet 0xTUWALLET
```

Genera un reporte HTML/JSON en `reports/`.

## Estructura de configuración

Archivo `config/polymarket_auto.json`:

```json
{
  "bankroll": 100.0,
  "cities": [
    "London",
    "New York",
    "NYC",
    "Paris",
    "Tokyo",
    "Los Angeles",
    "Chicago",
    "Seoul"
  ],
  "min_price": 0.001,
  "max_price": 0.1,
  "min_liquidity": 50.0,
  "min_edge_pct": 0.2,
  "deviation": 3.5,
  "stake_pct": 0.05,
  "max_stake": 10.0,
  "markets_limit": 200
}
```

## Nota

Este bot solo **simula** operaciones; no coloca trades reales en Polymarket.
