import streamlit as st
import requests
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Bot de Análisis Técnico OKX", page_icon="📈", layout="wide")

st.title("🤖 Bot de Análisis Técnico para OKX (Futuros y Spot)")
st.markdown("Herramienta analítica con buscador escrito para evaluar **Spot** y **Futuros (SWAP)** por separado.")


# Función para obtener TODOS los instrumentos (Swaps y Spot en USDT) de OKX
@st.cache_data(ttl=3600)
def get_okx_all_symbols():
    fallback_symbols = [
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
        "DOGE-USDT-SWAP", "ADA-USDT-SWAP", "AVAX-USDT-SWAP", "LINK-USDT-SWAP",
        "BNB-USDT-SWAP", "SUI-USDT-SWAP", "PEPE-USDT-SWAP", "SHIB-USDT-SWAP",
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT"
    ]
    try:
        symbols = []
        for inst_type in ["SWAP", "SPOT"]:
            url = f"https://www.okx.com/api/v5/public/instruments?instType={inst_type}"
            response = requests.get(url, timeout=5)
            data = response.json()
            if data.get("code") == "0" and len(data.get("data", [])) > 0:
                filtered = [item["instId"] for item in data["data"] if item.get("quoteCcy") == "USDT"]
                symbols.extend(filtered)

        if symbols:
            return sorted(list(set(symbols)))
    except Exception:
        pass

    return sorted(fallback_symbols)


def extraer_base_asset(texto_o_par: str) -> str:
    """Extrae la moneda base (ej: 'BTC-USDT-SWAP' -> 'BTC', 'pepe' -> 'PEPE')."""
    limpio = texto_o_par.strip().upper()
    if "-USDT-SWAP" in limpio:
        return limpio.replace("-USDT-SWAP", "")
    if "-USDT" in limpio:
        return limpio.replace("-USDT", "")
    if "-" in limpio:
        return limpio.split("-")[0]
    return limpio


def fmt_precio(valor: float) -> str:
    """Formatea precios grandes con 2-4 decimales y precios pequeños con más precisión."""
    if abs(valor) >= 10:
        return f"${valor:,.2f}"
    if abs(valor) >= 0.01:
        return f"${valor:,.4f}"
    return f"${valor:,.6f}"


# Función para obtener velas históricas de OKX
@st.cache_data(ttl=300)
def get_okx_candles(inst_id, bar, limit=150):
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("code") == "0" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(
                data["data"],
                columns=["ts", "o", "high", "low", "c", "vol", "volCcy", "volCcyQuote", "confirm"]
            )
            df = df.iloc[::-1].reset_index(drop=True)

            df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
            for col in ["o", "high", "low", "c", "vol"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["ts", "c", "high", "low"])
            if not df.empty:
                return df
    except Exception:
        pass
    return None


def calcular_analisis(df: pd.DataFrame) -> dict:
    close = df["c"]
    high = df["high"]
    low = df["low"]

    # Cálculos técnicos (EMA 50, EMA 200, RSI 14, ATR 14)
    ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.fillna(50).iloc[-1])

    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1
    ).max(axis=1)
    atr = float(tr.rolling(window=14).mean().iloc[-1])

    current_price = float(close.iloc[-1])
    recent_low = float(low.iloc[-10:].min())
    recent_high = float(high.iloc[-10:].max())

    # Puntuación para determinar sesgo
    score = 0
    if current_price > ema_50:
        score += 1
    if ema_50 > ema_200:
        score += 2
    if rsi < 30:
        score += 1
    elif rsi > 70:
        score -= 1

    if score > 0:
        bias_corto = "ALCISTA"
        bias = "ALCISTA (Mayor probabilidad de Subida)"
        entry_limit = round(recent_low + (atr * 0.3), 6)
        stop_loss = round(entry_limit - (atr * 1.5), 6)
        take_profit = round(entry_limit + ((entry_limit - stop_loss) * 2.5), 6)
        color = "green"
    else:
        bias_corto = "BAJISTA"
        bias = "BAJISTA (Mayor probabilidad de Bajada)"
        entry_limit = round(recent_high - (atr * 0.3), 6)
        stop_loss = round(entry_limit + (atr * 1.5), 6)
        take_profit = round(entry_limit - ((stop_loss - entry_limit) * 2.5), 6)
        color = "red"

    return {
        "current_price": current_price,
        "ema_50": float(ema_50),
        "ema_200": float(ema_200),
        "rsi": rsi,
        "atr": atr,
        "score": score,
        "bias_corto": bias_corto,
        "bias": bias,
        "entry_limit": entry_limit,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "color": color,
    }


def construir_tabla_resumen(spot_pair: str, df_spot: pd.DataFrame | None, swap_pair: str, df_swap: pd.DataFrame | None) -> pd.DataFrame:
    filas = []

    for mercado, inst_id, df in [
        ("Spot", spot_pair, df_spot),
        ("Futuros (SWAP)", swap_pair, df_swap),
    ]:
        if df is not None and not df.empty:
            res = calcular_analisis(df)
            filas.append({
                "Mercado": mercado,
                "Par": inst_id,
                "Precio Actual": fmt_precio(res["current_price"]),
                "Sesgo": res["bias_corto"],
                "Score": res["score"],
                "Entrada (Limit)": fmt_precio(res["entry_limit"]),
                "Stop Loss (SL)": fmt_precio(res["stop_loss"]),
                "Take Profit (TP)": fmt_precio(res["take_profit"]),
                "RSI (14)": round(res["rsi"], 2),
                "EMA 50": fmt_precio(res["ema_50"]),
                "EMA 200": fmt_precio(res["ema_200"]),
                "ATR (14)": fmt_precio(res["atr"]),
            })
        else:
            filas.append({
                "Mercado": mercado,
                "Par": inst_id,
                "Precio Actual": "N/D",
                "Sesgo": "Sin datos",
                "Score": None,
                "Entrada (Limit)": "N/D",
                "Stop Loss (SL)": "N/D",
                "Take Profit (TP)": "N/D",
                "RSI (14)": None,
                "EMA 50": "N/D",
                "EMA 200": "N/D",
                "ATR (14)": "N/D",
            })

    return pd.DataFrame(filas)


def render_resultado_mercado(titulo_mercado: str, inst_id: str, df: pd.DataFrame | None):
    st.subheader(f"{titulo_mercado} — `{inst_id}`")

    if df is None or df.empty:
        st.warning(f"No se encontraron datos de velas para `{inst_id}` en OKX.")
        return

    res = calcular_analisis(df)

    st.metric("Precio Actual", fmt_precio(res["current_price"]))
    st.markdown(f"**Sesgo:** :{res['color']}[{res['bias']}] (Score: `{res['score']}`)")

    c1, c2, c3 = st.columns(3)
    c1.metric("Entrada (Limit)", fmt_precio(res["entry_limit"]))
    c2.metric("Stop Loss (SL)", fmt_precio(res["stop_loss"]))
    c3.metric("Take Profit (TP)", fmt_precio(res["take_profit"]))

    with st.expander("Ver indicadores técnicos (EMA, RSI, ATR)"):
        st.write(f"- **EMA 50:** `{res['ema_50']:.6f}`")
        st.write(f"- **EMA 200:** `{res['ema_200']:.6f}`")
        st.write(f"- **RSI (14):** `{res['rsi']:.2f}`")
        st.write(f"- **ATR (14):** `{res['atr']:.6f}`")

    # Gráfico protegido
    try:
        chart_data = df.copy()
        chart_data["date"] = pd.to_datetime(chart_data["ts"], unit="ms", errors="coerce")
        chart_data = chart_data.dropna(subset=["date"])
        st.line_chart(chart_data.set_index("date")["c"], height=240)
    except Exception:
        st.line_chart(df["c"], height=240)


# Cargar la lista completa de criptomonedas disponibles en OKX
all_symbols = get_okx_all_symbols()
all_symbols_set = set(all_symbols)

# Barra lateral con buscador escrito e interactivo
st.sidebar.header("Configuración de Mercado")

busqueda_texto = st.sidebar.text_input("🔍 Escribe la cripto (ej: PEPE, BTC, SOL)", value="BTC")
busqueda_mayus = busqueda_texto.strip().upper()

simbolos_filtrados = [s for s in all_symbols if busqueda_mayus in s] if busqueda_mayus else all_symbols
if not simbolos_filtrados:
    simbolos_filtrados = all_symbols

selected_symbol = st.sidebar.selectbox(
    "Selecciona el par encontrado",
    simbolos_filtrados,
    help="Elige un par; el bot analizará automáticamente tanto su versión SPOT como FUTUROS (SWAP) si existen."
)

timeframe = st.sidebar.selectbox("Temporalidad", ["1H", "4H", "1D"], index=1)
vista_modo = st.sidebar.radio("Modo de visualización", ["Pestañas separadas", "Dos columnas lado a lado"])

base_asset = extraer_base_asset(
    selected_symbol if busqueda_mayus == "" else (busqueda_mayus if "-" not in busqueda_mayus else selected_symbol)
)
spot_pair = f"{base_asset}-USDT"
swap_pair = f"{base_asset}-USDT-SWAP"

st.sidebar.caption(f"Spot objetivo: `{spot_pair}` {'✅' if spot_pair in all_symbols_set else '⚠️'}")
st.sidebar.caption(f"Futuros objetivo: `{swap_pair}` {'✅' if swap_pair in all_symbols_set else '⚠️'}")

# Botón para ejecutar el análisis
if st.button("🚀 Ejecutar Análisis Técnico (Spot y Futuros)"):
    with st.spinner(f"Consultando {spot_pair} y {swap_pair} en {timeframe}..."):
        df_spot = get_okx_candles(spot_pair, timeframe)
        df_swap = get_okx_candles(swap_pair, timeframe)

    # Resumen comparativo rápido si ambos existen
    if df_spot is not None and df_swap is not None:
        precio_spot = float(df_spot["c"].iloc[-1])
        precio_swap = float(df_swap["c"].iloc[-1])
        diff_abs = precio_swap - precio_spot
        diff_pct = ((precio_swap - precio_spot) / precio_spot) * 100 if precio_spot else 0
        st.info(
            f"**Comparativa rápida {base_asset}/USDT ({timeframe}):** "
            f"Spot: `{fmt_precio(precio_spot)}` | Futuros: `{fmt_precio(precio_swap)}` | "
            f"Diferencia (Futuros - Spot): `{diff_abs:+,.6f}` (`{diff_pct:+.2f}%`)"
        )

    # Tabla resumen comparativa
    st.markdown(f"### 📋 Tabla Resumen — {base_asset}/USDT ({timeframe})")
    df_resumen = construir_tabla_resumen(spot_pair, df_spot, swap_pair, df_swap)
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    st.divider()

    # Detalle por mercado separado
    if vista_modo == "Pestañas separadas":
        tab_spot, tab_swap = st.tabs([f"🟢 SPOT ({spot_pair})", f"🟣 FUTUROS / SWAP ({swap_pair})"])
        with tab_spot:
            render_resultado_mercado("Mercado Spot", spot_pair, df_spot)
        with tab_swap:
            render_resultado_mercado("Mercado Futuros (Perpetuo SWAP)", swap_pair, df_swap)
    else:
        col_left, col_right = st.columns(2)
        with col_left:
            render_resultado_mercado("🟢 Mercado Spot", spot_pair, df_spot)
        with col_right:
            render_resultado_mercado("🟣 Mercado Futuros (SWAP)", swap_pair, df_swap)
