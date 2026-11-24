import asyncio
import ccxt.async_support as ccxt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

# Configuración de la página web
st.set_page_config(
    page_title="Terminal Cripto Pro - Futuros OKX (SMC & Limit)",
    page_icon="📊",
    layout="wide",
)

# --- CSS PERSONALIZADO (ESTILO DASHBOARD PROFESIONAL) ---
st.markdown(
    """
    <style>
    .main { background-color: #0b0e14; }

    .top-banner {
        background: linear-gradient(90deg, #1565c0 0%, #1e88e5 100%);
        padding: 15px 25px;
        border-radius: 8px;
        color: white;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .top-banner h2 {
        margin: 0;
        font-size: 1.3rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    .kpi-card {
        padding: 18px 20px;
        border-radius: 8px;
        color: white;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.25);
        margin-bottom: 10px;
        transition: transform 0.2s ease;
    }
    .kpi-card:hover { transform: translateY(-3px); }

    .card-green { background: linear-gradient(135deg, #2e7d32 0%, #4caf50 100%); }
    .card-red { background: linear-gradient(135deg, #c62828 0%, #ef5350 100%); }
    .card-blue { background: linear-gradient(135deg, #1565c0 0%, #29b6f6 100%); }
    .card-orange { background: linear-gradient(135deg, #ef6c00 0%, #ffa726 100%); }
    .card-pink { background: linear-gradient(135deg, #880e4f 0%, #d81b60 100%); }

    .kpi-title {
        font-size: 0.80rem;
        text-transform: uppercase;
        font-weight: 700;
        opacity: 0.9;
        margin-bottom: 6px;
        letter-spacing: 0.5px;
    }
    .kpi-value {
        font-size: 1.75rem;
        font-weight: 800;
        margin: 0;
    }
    .kpi-sub {
        font-size: 0.78rem;
        opacity: 0.85;
        margin-top: 4px;
    }

    .mini-stat {
        background-color: #151922;
        border: 1px solid #21262d;
        padding: 12px 16px;
        border-radius: 6px;
        text-align: center;
    }
    .mini-stat-label { color: #8b949e; font-size: 0.75rem; text-transform: uppercase; }
    .mini-stat-val { color: #f0f6fc; font-size: 1.25rem; font-weight: 700; }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #151922;
        padding: 6px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #c9d1d9;
        padding: 8px 18px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1565c0 !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- BARRA LATERAL (CONFIGURACIÓN, BUSCADOR, DIRECCIÓN Y ALERTAS) ---
st.sidebar.header("⚙️ Panel de Control (OKX Futuros)")
modo_escaneo = st.sidebar.radio(
    "Modo de Operación:",
    [
        "Buscar Moneda Específica (Seguimiento)",
        "Top Futuros por Volumen (Alta Liquidez)",
        "Mi Watchlist Personalizada",
    ],
)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Plan de Trading & Liquidez")
direccion_trading = st.sidebar.selectbox(
    "Dirección de la Operación:",
    ["📈 Alcista (Long)", "📉 Bajista (Short)"],
)

vol_minimo = st.sidebar.number_input(
    "Volumen Mínimo 24h (USDT):",
    min_value=0,
    value=50000,
    step=10000,
    help="Filtra contratos perpetuos con baja liquidez en OKX.",
)

watchlist_default = (
    "BTC/USDT:USDT\nETH/USDT:USDT\nSOL/USDT:USDT\nXRP/USDT:USDT\nDOGE/USDT:USDT"
)
simbolos_personalizados = None
moneda_buscada = None

if modo_escaneo == "Buscar Moneda Específica (Seguimiento)":
    st.sidebar.subheader("🔎 Buscador en Futuros OKX")
    input_moneda = st.sidebar.text_input(
        "Ticker (ej. SOL, BTC, ETH):",
        value="SOL",
    )
    if input_moneda.strip():
        ticker_limpio = input_moneda.strip().upper()
        if ":" not in ticker_limpio:
            if "/" not in ticker_limpio:
                ticker_limpio = f"{ticker_limpio}/USDT:USDT"
            else:
                ticker_limpio = f"{ticker_limpio}:USDT"
        moneda_buscada = ticker_limpio
        simbolos_personalizados = [moneda_buscada]

elif modo_escaneo == "Mi Watchlist Personalizada":
    user_watchlist = st.sidebar.text_area(
        "Tu lista de futuros (PAR/USDT:USDT):",
        watchlist_default,
        height=130,
    )
    simbolos_personalizados = [
        s.strip().upper() for s in user_watchlist.split("\n") if s.strip()
    ]

st.sidebar.markdown("---")
with st.sidebar.expander("🔔 Alertas a Telegram (Opcional)"):
    activar_telegram = st.checkbox("Activar envío de señales")
    tg_token = st.text_input("Bot Token de Telegram:", type="password")
    tg_chat_id = st.text_input("Tu Chat ID:")
    umbral_alerta = st.slider("Enviar si Confluencia >=", 60, 95, 78)


# --- FUNCIONES DE CÁLCULO INSTITUCIONAL (VWAP, FVG/OB, POC, MACD) ---
def enviar_alerta_telegram(token, chat_id, mensaje):
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def calcular_macd_hist(df):
    close = df["close"]
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return hist.iloc[-1]


def calcular_vwap(df):
    """Calcula el VWAP (Volume Weighted Average Price) institucional."""
    try:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()
        return round(vwap.iloc[-1], 4)
    except Exception:
        return df["close"].iloc[-1]


def detectar_fvg_y_ob(df, direccion):
    """Detecta niveles de Fair Value Gap (FVG) / Order Block aproximados para entradas en retroceso."""
    try:
        close_actual = df["close"].iloc[-1]
        if "Short" in direccion:
            fvg_zona = df["high"].rolling(5).max().iloc[-2]
            return round(fvg_zona, 4)
        else:
            fvg_zona = df["low"].rolling(5).min().iloc[-2]
            return round(fvg_zona, 4)
    except Exception:
        return close_actual


def calcular_perfil_volumen_ponderado(df):
    """Calcula el Punto de Control (POC) ponderado por precio típico y volumen."""
    try:
        if len(df) == 0:
            return 0
        precio_min, precio_max = df["low"].min(), df["high"].max()
        if precio_min == precio_max:
            return df["close"].iloc[-1]

        bins = np.linspace(precio_min, precio_max, 20)
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["bin"] = pd.cut(typical_price, bins=bins, include_lowest=True)

        vol_por_bin = df.groupby("bin", observed=False)["volume"].sum()
        if vol_por_bin.empty or vol_por_bin.max() == 0:
            return df["close"].iloc[-1]

        poc_bin = vol_por_bin.idxmax()
        poc_precio = (poc_bin.left + poc_bin.right) / 2
        return round(poc_precio, 4)
    except Exception:
        return df["close"].iloc[-1]


async def analizar_simbolo(exchange, symbol, semaphore, direccion, vol_24h=0):
    async with semaphore:
        try:
            v_15m, v_1h, v_4h = await asyncio.gather(
                exchange.fetch_ohlcv(symbol, timeframe="15m", limit=50),
                exchange.fetch_ohlcv(symbol, timeframe="1h", limit=50),
                exchange.fetch_ohlcv(symbol, timeframe="4h", limit=50),
            )

            if len(v_15m) < 35 or len(v_1h) < 35 or len(v_4h) < 35:
                return None

            df_15m = pd.DataFrame(
                v_15m, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df_1h = pd.DataFrame(
                v_1h, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df_4h = pd.DataFrame(
                v_4h, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

            precio_actual = df_1h["close"].iloc[-1]
            precio_anterior = df_1h["close"].iloc[-2]
            cambio_1h = ((precio_actual - precio_anterior) / precio_anterior) * 100

            close_1h = df_1h["close"]
            delta = close_1h.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi_actual = rsi_series.iloc[-1] if not rsi_series.empty else 50.0

            sma_20 = close_1h.rolling(20).mean()
            std_20 = close_1h.rolling(20).std()
            upper = (sma_20 + (2 * std_20)).iloc[-1]
            lower = (sma_20 - (2 * std_20)).iloc[-1]
            sma = sma_20.iloc[-1]

            macd_15m = calcular_macd_hist(df_15m)
            macd_1h = calcular_macd_hist(df_1h)
            macd_4h = calcular_macd_hist(df_4h)

            alcista_15m = (
                precio_actual > df_15m["close"].rolling(20).mean().iloc[-1]
            )
            alcista_1h = precio_actual > sma
            alcista_4h = precio_actual > df_4h["close"].rolling(20).mean().iloc[-1]

            puntos_alcistas = 50
            puntos_alcistas += 8 if alcista_4h else -8
            puntos_alcistas += 6 if alcista_1h else -6
            puntos_alcistas += 4 if alcista_15m else -4

            puntos_alcistas += 12 if macd_4h > 0 else -12
            puntos_alcistas += 9 if macd_1h > 0 else -9
            puntos_alcistas += 6 if macd_15m > 0 else -6

            if not np.isnan(lower) and not np.isnan(upper):
                if precio_actual <= lower * 1.01:
                    puntos_alcistas += 8
                elif precio_actual >= upper * 0.99:
                    puntos_alcistas -= 8

            if not np.isnan(rsi_actual):
                if rsi_actual < 30:
                    puntos_alcistas += 6
                elif rsi_actual > 70:
                    puntos_alcistas -= 6

            prob_subir = max(0, min(100, int(puntos_alcistas)))
            conteo_tendencia = sum([alcista_15m, alcista_1h, alcista_4h])

            if conteo_tendencia == 3:
                tendencia_txt = "Alcista Fuerte"
            elif conteo_tendencia == 2:
                tendencia_txt = "Alcista Moderada"
            elif conteo_tendencia == 1:
                tendencia_txt = "Bajista Moderada"
            else:
                tendencia_txt = "Bajista Fuerte"

            poc = calcular_perfil_volumen_ponderado(df_1h)
            vwap = calcular_vwap(df_1h)
            fvg_ob = detectar_fvg_y_ob(df_1h, direccion)

            if "Short" in direccion:
                limit_entry = round(max(poc, vwap, fvg_ob, upper * 1.002), 4)
                stop_loss = round(max(upper * 1.01, limit_entry * 1.02), 4)
                riesgo = stop_loss - limit_entry
                if riesgo <= 0:
                    stop_loss = round(limit_entry * 1.03, 4)
                    riesgo = stop_loss - limit_entry
                take_profit = round(limit_entry - (riesgo * 2.0), 4)
                take_profit = max(0.0001, take_profit)
            else:
                limit_entry = round(min(poc, vwap, fvg_ob, lower * 0.998), 4)
                stop_loss = round(min(lower * 0.99, limit_entry * 0.98), 4)
                riesgo = limit_entry - stop_loss
                if riesgo <= 0:
                    stop_loss = round(limit_entry * 0.97, 4)
                    riesgo = limit_entry - stop_loss
                take_profit = round(limit_entry + (riesgo * 2.0), 4)

            vol_compra = df_1h[df_1h["close"] >= df_1h["open"]]["volume"].sum()
            vol_venta = df_1h[df_1h["close"] < df_1h["open"]]["volume"].sum()

            return {
                "Cripto": symbol.split(":")[0],
                "Precio ($)": round(precio_actual, 4),
                "Precio Limit ($)": limit_entry,
                "Volumen 24h ($)": round(vol_24h, 0),
                "Cambio_1h": round(cambio_1h, 2),
                "Tendencia (3T)": tendencia_txt,
                "POC (Vol)": poc,
                "VWAP": vwap,
                "FVG/OB": fvg_ob,
                "Prob_Subir_Num": prob_subir,
                "Prob. Subir": f"{prob_subir}%",
                "Stop Loss ($)": stop_loss,
                "Take Profit ($)": take_profit,
                "MACD 15m": "🟢 Alcista" if macd_15m > 0 else "🔴 Bajista",
                "MACD 1h": "🟢 Alcista" if macd_1h > 0 else "🔴 Bajista",
                "MACD 4h": "🟢 Alcista" if macd_4h > 0 else "🔴 Bajista",
                "RSI (1h)": round(rsi_actual, 1),
                "vol_compra": vol_compra,
                "vol_venta": vol_venta,
                "raw_df": df_1h,
            }
        except Exception:
            return None


async def _ejecutar_escaneo_async(simbolos_custom, direccion, vol_min):
    exchange_okx = ccxt.okx(
        {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    )
    try:
        await exchange_okx.load_markets()
        tickers = await exchange_okx.fetch_tickers()

        if simbolos_custom:
            simbolos_a_escanear = []
            for s in simbolos_custom:
                if s in exchange_okx.markets and exchange_okx.markets[s]["active"]:
                    t_data = tickers.get(s, {})
                    v24 = (
                        t_data.get("quoteVolume", 0)
                        or t_data.get("baseVolume", 0) * t_data.get("last", 1)
                        or 0
                    )
                    if "BTC/USDT" in s or v24 >= vol_min or v24 == 0:
                        simbolos_a_escanear.append((s, v24))

            btc_key = next(
                (s for s in exchange_okx.markets if "BTC/USDT" in s), "BTC/USDT:USDT"
            )
            if not any(item[0] == btc_key for item in simbolos_a_escanear):
                t_btc = tickers.get(btc_key, {})
                btc_vol = (
                    t_btc.get("quoteVolume", 0)
                    or t_btc.get("baseVolume", 0) * t_btc.get("last", 1)
                    or 0
                )
                simbolos_a_escanear.insert(0, (btc_key, btc_vol))
        else:
            pares_volumen = []
            for s, m in exchange_okx.markets.items():
                if m["active"] and s in tickers and "/USDT" in s:
                    t_data = tickers[s]
                    volumen_24h = (
                        t_data.get("quoteVolume", 0)
                        or t_data.get("baseVolume", 0) * t_data.get("last", 1)
                        or 0
                    )
                    if "BTC/USDT" in s or volumen_24h >= vol_min:
                        pares_volumen.append((s, volumen_24h))

            pares_volumen.sort(key=lambda x: x[1], reverse=True)
            simbolos_a_escanear = pares_volumen[:100]

            btc_key = next(
                (s for s, _ in simbolos_a_escanear if "BTC/USDT" in s),
                "BTC/USDT:USDT",
            )
            simbolos_a_escanear = [
                item for item in simbolos_a_escanear if "BTC/USDT" not in item[0]
            ]
            t_btc = tickers.get(btc_key, {})
            btc_vol = (
                t_btc.get("quoteVolume", 0)
                or t_btc.get("baseVolume", 0) * t_btc.get("last", 1)
                or 0
            )
            simbolos_a_escanear.insert(0, (btc_key, btc_vol))

        semaphore = asyncio.Semaphore(8)
        tareas = [
            analizar_simbolo(exchange_okx, s, semaphore, direccion, v24)
            for s, v24 in simbolos_a_escanear
        ]
        resultados = await asyncio.gather(*tareas)
        resultados_validos = [r for r in resultados if r is not None]

        def ordenar_btc_primero(x):
            if "BTC" in x["Cripto"]:
                return (-1, -x["Prob_Subir_Num"])
            return (0, -x["Prob_Subir_Num"])

        resultados_validos.sort(key=ordenar_btc_primero)
        return resultados_validos

    finally:
        await exchange_okx.close()


@st.cache_data(ttl=120, show_spinner=False)
def obtener_datos_cacheados(simbolos_tuple, direccion, vol_min):
    simbolos_list = list(simbolos_tuple) if simbolos_tuple else None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        _ejecutar_escaneo_async(simbolos_list, direccion, vol_min)
    )


# --- BANNER SUPERIOR ---
st.markdown(
    f"""
    <div class="top-banner">
        <h2>📊 TERMINAL FUTUROS PRO (OKX) — MODO PLAN ({direccion_trading.upper()})</h2>
        <span style="font-size: 0.85rem; opacity: 0.9;">Exchange: OKX Futures | SMC (VWAP + FVG/OB + POC)</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- BOTÓN DE EJECUCIÓN ---
col_btn1, col_btn2 = st.sidebar.columns([3, 1])
texto_boton = (
    f"🔄 Escanear {moneda_buscada}"
    if modo_escaneo == "Buscar Moneda Específica (Seguimiento)"
    and moneda_buscada
    else "🔍 Escanear Mercado OKX"
)

btn_escanear = col_btn1.button(
    texto_boton, type="primary", use_container_width=True
)
if col_btn2.button("🧹", help="Limpiar caché de futuros"):
    st.cache_data.clear()
    st.toast("Caché limpiada.")

if btn_escanear:
    if (
        modo_escaneo == "Buscar Moneda Específica (Seguimiento)"
        and not moneda_buscada
    ):
        st.warning("Escribe el nombre de un contrato en el buscador.")
    else:
        with st.spinner("Sincronizando contratos perpetuos con OKX Futuros..."):
            simb_tupla = (
                tuple(simbolos_personalizados) if simbolos_personalizados else None
            )
            destacados = obtener_datos_cacheados(
                simb_tupla, direccion_trading, vol_minimo
            )

        if destacados:
            if activar_telegram and tg_token and tg_chat_id:
                alertas_enviadas = 0
                for r in destacados:
                    if "BTC" not in r["Cripto"] and r["Prob_Subir_Num"] >= umbral_alerta:
                        msg = (
                            f"🚨 *ALERTA INSTITUCIONAL (OKX)*\n\n"
                            f"🪙 *Activo:* {r['Cripto']}\n"
