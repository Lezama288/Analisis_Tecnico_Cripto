import streamlit as st
import requests
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Bot de Análisis de Futuros OKX", page_icon="📈", layout="centered")

st.title("🤖 Bot de Análisis Técnico para Futuros OKX")
st.markdown("Herramienta analítica con buscador para evaluar el sesgo de mercado y niveles operativos (Limit, SL, TP).")

# Función para obtener dinámicamente TODOS los futuros / swaps en USDT de OKX
@st.cache_data(ttl=3600)
def get_okx_futures_symbols():
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    try:
        response = requests.get(url)
        data = response.json()
        if data["code"] == "0":
            # Filtrar contratos cuyo margen/cotización sea en USDT (ej: BTC-USDT-SWAP)
            symbols = [item["instId"] for item in data["data"] if item.get("quoteCcy") == "USDT"]
            return sorted(symbols)
    except Exception:
        pass
    # Lista de respaldo por si falla la conexión inicial
    return ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP"]

# Cargar la lista de criptomonedas a futuro disponibles
all_symbols = get_okx_futures_symbols()

# Barra lateral para configuraciones del usuario con buscador integrado
st.sidebar.header("Configuración de Mercado")

# Streamlit selectbox permite escribir directamente para buscar en la lista
default_index = all_symbols.index("BTC-USDT-SWAP") if "BTC-USDT-SWAP" in all_symbols else 0
symbol = st.sidebar.selectbox(
    "🔍 Escribe o selecciona la Criptomoneda", 
    all_symbols, 
    index=default_index,
    help="Puedes escribir directamente el nombre (ej: DOGE, ADA, BTC) para buscar el par a futuro."
)

timeframe = st.sidebar.selectbox("Temporalidad", ["1H", "4H", "1D"], index=1)

# Función para obtener velas históricas de OKX
@st.cache_data(ttl=300)
def get_okx_candles(inst_id, bar, limit=150):
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    if data["code"] == "0":
        df = pd.DataFrame(data["data"], columns=["ts", "o", "high", "low", "c", "vol", "volCcy", "volCcyQuote", "confirm"])
        df = df.iloc[::-1].reset_index(drop=True)
        for col in ["o", "high", "low", "c", "vol"]:
            df[col] = pd.to_numeric(df[col])
        return df
    else:
        st.error("Error al conectar con la API de OKX para este símbolo.")
        return None

# Botón para ejecutar el análisis
if st.button("🚀 Ejecutar Análisis de Futuros"):
    with st.spinner(f"Analizando {symbol} en temporalidad {timeframe}..."):
        df = get_okx_candles(symbol, timeframe)
        
        if df is not None and not df.empty:
            close = df["c"]
            high = df["high"]
            low = df["low"]
            
            # Cálculos técnicos
            ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
            ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
            
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
            
            tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1]
            
            current_price = close.iloc[-1]
            recent_low = low.iloc[-10:].min()
            recent_high = high.iloc[-10:].max()
            
            # Sistema de puntuación para sesgo de probabilidad
            score = 0
            if current_price > ema_50: score += 1
            if ema_50 > ema_200: score += 2
            if rsi < 30: score += 1
            elif rsi > 70: score -= 1
            
            if score > 0:
                bias = "ALCISTA (Mayor probabilidad de Subida)"
                entry_limit = round(recent_low + (atr * 0.3), 4)
                stop_loss = round(entry_limit - (atr * 1.5), 4)
                take_profit = round(entry_limit + ((entry_limit - stop_loss) * 2.5), 4)
                color = "green"
            else:
                bias = "BAJISTA (Mayor probabilidad de Bajada)"
                entry_limit = round(recent_high - (atr * 0.3), 4)
                stop_loss = round(entry_limit + (atr * 1.5), 4)
                take_profit = round(entry_limit - ((stop_loss - entry_limit) * 2.5), 4)
                color = "red"
            
            # Mostrar métricas en la interfaz
            st.metric("Precio Actual del Futuro", f"${current_price:,.4f}")
            st.markdown(f"### Sesgo: :{color}[{bias}]")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Entrada (Limit)", f"${entry_limit:,.4f}")
            col2.metric("Stop Loss (SL)", f"${stop_loss:,.4f}")
            col3.metric("Take Profit (TP)", f"${take_profit:,.4f}")
            
            # Gráfico de la evolución del precio
            st.line_chart(df.set_index(pd.to_datetime(df["ts"], unit="ms"))["c"])
