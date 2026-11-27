import streamlit as st
import requests
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Bot de Análisis Técnico OKX", page_icon="📈", layout="wide")

st.title("🤖 Bot de Análisis Técnico para OKX (Futuros y Spot)")
st.markdown("Herramienta analítica con buscador escrito para evaluar **Spot** y **Futuros (SWAP)** por separado, con viñetas explicativas en cada dato.")

# Diccionario de explicaciones para las viñetas de cada información
EXPLICACIONES = {
    "precio_actual": "Último precio de cierre de la vela más reciente en el mercado seleccionado.",
    "diferencia_basis": "Diferencia entre el precio de Futuros (SWAP) y Spot. Un valor positivo indica que Futuros cotiza por encima de Spot (prima/contango); negativo indica descuento.",
    "sesgo": "Dirección probable según la puntuación combinada de medias móviles (EMA 50/200) y momentum (RSI 14).",
    "score": "Suma de puntos técnicos: +1 si precio > EMA 50, +2 si EMA 50 > EMA 200, +1 si RSI < umbral de sobreventa y -1 si RSI > umbral de sobrecompra.",
    "entrada_limit": "Nivel sugerido de orden límite calculado desde el mínimo reciente (en sesgo alcista) o máximo reciente (en sesgo bajista) ajustado con el multiplicador de entrada por ATR.",
    "stop_loss": "Nivel de invalidación/protección calculado alejando la entrada según el multiplicador de Stop Loss por ATR para limitar pérdidas.",
    "take_profit": "Objetivo de toma de ganancias calculado proyectando la distancia del riesgo (Entrada - SL) multiplicada por el ratio/multiplicador de Take Profit.",
    "ema_50": "Media Móvil Exponencial de 50 periodos: refleja la tendencia de corto/medio plazo dando más peso a las velas recientes.",
    "ema_200": "Media Móvil Exponencial de 200 periodos: referencia clásica de tendencia macro o de fondo en la temporalidad elegida.",
    "rsi_14": "Índice de Fuerza Relativa de 14 periodos (0 a 100): mide velocidad y cambio de movimientos para detectar zonas extremas o impulso.",
    "atr_14": "Average True Range de 14 periodos: mide la volatilidad promedio por vela (en unidades de precio) para dimensionar entradas, SL y TP.",
    "tabla_resumen": "Compara en una sola vista el estado de Spot y Futuros (SWAP): precio, sesgo, score, niveles operativos (Limit, SL, TP) e indicadores.",
}


def viñeta_explicacion(clave: str, etiqueta_boton: str = "ℹ️"):
    """Muestra una viñeta interactiva con la explicación del dato."""
    texto = EXPLICACIONES.get(clave, "Sin explicación disponible.")
    with st.popover(etiqueta_boton):
        st.caption(texto)


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


def calcular_analisis(df: pd.DataFrame, cfg: dict) -> dict:
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

    # Puntuación configurable para determinar sesgo
    score = 0
    if current_price > ema_50:
        score += cfg["peso_ema50"]
    if ema_50 > ema_200:
        score += cfg["peso_ema200"]
    if rsi < cfg["rsi_oversold"]:
        score += cfg["peso_rsi"]
    elif rsi > cfg["rsi_overbought"]:
        score -= cfg["peso_rsi"]

    if score > 0:
        bias_corto = "ALCISTA"
        bias = "ALCISTA (Mayor probabilidad de Subida)"
        raw_entry = recent_low + (atr * cfg["mult_entry"])
        raw_sl = raw_entry - (atr * cfg["mult_sl"])
        raw_tp = raw_entry + ((raw_entry - max(0.0, raw_sl)) * cfg["mult_tp"])
        color = "green"
    else:
        bias_corto = "BAJISTA"
        bias = "BAJISTA (Mayor probabilidad de Bajada)"
        raw_entry = recent_high - (atr * cfg["mult_entry"])
        raw_sl = raw_entry + (atr * cfg["mult_sl"])
        raw_tp = raw_entry - ((max(0.0, raw_sl) - max(0.0, raw_entry)) * cfg["mult_tp"])
        color = "red"

    # Evitar precios en cero o negativos en activos de precio muy bajo
    alerta_cero = (raw_entry <= 0) or (raw_sl <= 0) or (raw_tp <= 0)
    entry_limit = round(max(0.0, raw_entry), 6)
    stop_loss = round(max(0.0, raw_sl), 6)
    take_profit = round(max(0.0, raw_tp), 6)

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
        "alerta_cero": alerta_cero,
        "color": color,
    }


def construir_tabla_resumen(spot_pair: str, df_spot: pd.DataFrame | None, swap_pair: str, df_swap: pd.DataFrame | None, cfg: dict) -> pd.DataFrame:
    filas = []

    for mercado, inst_id, df in [
        ("Spot", spot_pair, df_spot),
        ("Futuros (SWAP)", swap_pair, df_swap),
    ]:
        if df is not None and not df.empty:
            res = calcular_analisis(df, cfg)
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


def render_resultado_mercado(titulo_mercado: str, inst_id: str, df: pd.DataFrame | None, cfg: dict):
    st.subheader(f"{titulo_mercado} — `{inst_id}`")

    if df is None or df.empty:
        st.warning(f"No se encontraron datos de velas para `{inst_id}` en OKX.")
        return

    res = calcular_analisis(df, cfg)

    if res["alerta_cero"]:
        st.warning(
            "Uno o más niveles calculados (Limit, SL o TP) llegaron a 0 o menos por el multiplicador de ATR en un activo de precio bajo; se ajustaron a $0 para evitar valores negativos."
        )

    # Precio actual + viñeta
    p_col, p_pop = st.columns([5, 1])
    with p_col:
        st.metric("Precio Actual", fmt_precio(res["current_price"]))
    with p_pop:
        st.write("")
        viñeta_explicacion("precio_actual")

    # Sesgo y Score + viñetas
    s_col, s_pop1, s_pop2 = st.columns([6, 1, 1])
    with s_col:
        st.markdown(f"**Sesgo:** :{res['color']}[{res['bias']}] | **Score:** `{res['score']}`")
    with s_pop1:
        viñeta_explicacion("sesgo", "ℹ️ Sesgo")
    with s_pop2:
        viñeta_explicacion("score", "ℹ️ Score")

    # Niveles operativos (Limit, SL, TP) + viñeta por cada uno
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Entrada (Limit)", fmt_precio(res["entry_limit"]))
        viñeta_explicacion("entrada_limit", "ℹ️ Qué es Limit")
    with c2:
        st.metric("Stop Loss (SL)", fmt_precio(res["stop_loss"]))
        viñeta_explicacion("stop_loss", "ℹ️ Qué es SL")
    with c3:
        st.metric("Take Profit (TP)", fmt_precio(res["take_profit"]))
        viñeta_explicacion("take_profit", "ℹ️ Qué es TP")

    # Indicadores técnicos con viñeta individual para cada uno
    with st.expander("Ver indicadores técnicos (EMA, RSI, ATR) con explicación"):
        for etiqueta, valor_txt, clave_exp in [
            ("EMA 50", f"`{res['ema_50']:.6f}`", "ema_50"),
            ("EMA 200", f"`{res['ema_200']:.6f}`", "ema_200"),
            ("RSI (14)", f"`{res['rsi']:.2f}`", "rsi_14"),
            ("ATR (14)", f"`{res['atr']:.6f}`", "atr_14"),
        ]:
            i_col, i_pop = st.columns([6, 1])
            with i_col:
                st.write(f"- **{etiqueta}:** {valor_txt}")
            with i_pop:
                viñeta_explicacion(clave_exp)

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

with st.sidebar.expander("⚙️ Ajustes de Cálculo (ATR y Sesgo)"):
    mult_entry = st.slider("Multiplicador Entrada (ATR)", 0.0, 2.0, 0.3, 0.1)
    mult_sl = st.slider("Multiplicador Stop Loss (ATR)", 0.5, 5.0, 1.5, 0.1)
    mult_tp = st.slider("Multiplicador Take Profit (R)", 1.0, 6.0, 2.5, 0.1)
    peso_ema50 = st.number_input("Peso Precio > EMA 50", 0, 5, 1)
    peso_ema200 = st.number_input("Peso EMA 50 > EMA 200", 0, 5, 2)
    peso_rsi = st.number_input("Peso RSI extremo", 0, 5, 1)
    rsi_oversold = st.slider("Umbral RSI Sobreventa (<)", 10, 45, 30, 1)
    rsi_overbought = st.slider("Umbral RSI Sobrecompra (>)", 55, 90, 70, 1)

cfg = {
    "mult_entry": mult_entry,
    "mult_sl": mult_sl,
    "mult_tp": mult_tp,
    "peso_ema50": peso_ema50,
    "peso_ema200": peso_ema200,
    "peso_rsi": peso_rsi,
    "rsi_oversold": rsi_oversold,
    "rsi_overbought": rsi_overbought,
}

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
        c_info, c_pop = st.columns([11, 1])
        with c_info:
            st.info(
                f"**Comparativa rápida {base_asset}/USDT ({timeframe}):** "
                f"Spot: `{fmt_precio(precio_spot)}` | Futuros: `{fmt_precio(precio_swap)}` | "
                f"Diferencia (Futuros - Spot): `{diff_abs:+,.6f}` (`{diff_pct:+.2f}%`)"
            )
        with c_pop:
            st.write("")
            viñeta_explicacion("diferencia_basis")

    # Tabla resumen comparativa con viñeta explicativa y glosario de columnas
    t_col, t_pop = st.columns([11, 1])
    with t_col:
        st.markdown(f"### 📋 Tabla Resumen — {base_asset}/USDT ({timeframe})")
    with t_pop:
        st.write("")
        viñeta_explicacion("tabla_resumen")

    df_resumen = construir_tabla_resumen(spot_pair, df_spot, swap_pair, df_swap, cfg)
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    with st.popover("ℹ️ Explicación de cada columna de la tabla resumen"):
        for col_name, clave_exp in [
            ("Precio Actual", "precio_actual"),
            ("Sesgo", "sesgo"),
            ("Score", "score"),
            ("Entrada (Limit)", "entrada_limit"),
            ("Stop Loss (SL)", "stop_loss"),
            ("Take Profit (TP)", "take_profit"),
            ("RSI (14)", "rsi_14"),
            ("EMA 50", "ema_50"),
            ("EMA 200", "ema_200"),
            ("ATR (14)", "atr_14"),
        ]:
            st.markdown(f"- **{col_name}:** {EXPLICACIONES[clave_exp]}")

    st.divider()

    # Detalle por mercado separado
    if vista_modo == "Pestañas separadas":
        tab_spot, tab_swap = st.tabs([f"🟢 SPOT ({spot_pair})", f"🟣 FUTUROS / SWAP ({swap_pair})"])
        with tab_spot:
            render_resultado_mercado("Mercado Spot", spot_pair, df_spot, cfg)
        with tab_swap:
            render_resultado_mercado("Mercado Futuros (Perpetuo SWAP)", swap_pair, df_swap, cfg)
    else:
        col_left, col_right = st.columns(2)
        with col_left:
            render_resultado_mercado("🟢 Mercado Spot", spot_pair, df_spot, cfg)
        with col_right:
            render_resultado_mercado("🟣 Mercado Futuros (SWAP)", swap_pair, df_swap, cfg)
