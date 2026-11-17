import streamlit as st
import requests
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Bot de Análisis Técnico OKX", page_icon="📈", layout="centered")

st.title("🤖 Bot de Análisis Técnico y Probabilidades (OKX)")
st.markdown("Herramienta analítica para evaluar el sesgo de mercado y niveles operativos (Limit, SL, TP).")

# Barra lateral para configuraciones del usuario
st.sidebar.header("Configuración")
symbol = st.sidebar.selectbox("Selecciona la Criptomoneda", ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT"])
timeframe = st.sidebar.selectbox("Temporalidad", ["1H", "4H", "1D"], index=1)

# Función para obtener datos de OKX
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
        st.error("Error al conectar con la API de OKX")
        return None

# Botón para ejecutar el análisis
if st.button("🚀 Ejecutar Análisis de Mercado"):
    with st.spinner(f"Analizando {symbol} en temporalidad {timeframe}..."):
        df = get_okx_candles(symbol, timeframe)
        
        if df is not None:
            close = df["c"]
            high = df["high"]
            low = df["low"]
            
            ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
            ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
            
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
            
            # Línea corregida con los paréntesis correctos
            tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean().iloc[-1]
            
            current_price = close.iloc[-1]
            recent_low = low.iloc[-10:].min()
            recent_high = high.iloc[-10:].max()
            
            score = 0
            if current_price > ema_50: score += 1
            if ema_50 > ema_200: score += 2
            if rsi < 30: score += 1
            elif rsi > 70: score -= 1
            
            if score > 0:
                bias = "ALCISTA (Mayor probabilidad de Subida)"
                entry_limit = round(recent_low + (atr * 0.3), 2)
                stop_loss = round(entry_limit - (atr * 1.5), 2)
                take_profit = round(entry_limit + ((entry_limit - stop_loss) * 2.5), 2)
                color = "green"
            else:
                bias = "BAJISTA (Mayor probabilidad de Bajada)"
                entry_limit = round(recent_high - (atr * 0.3), 2)
                stop_loss = round(entry_limit + (atr * 1.5), 2)
                take_profit = round(entry_limit - ((stop_loss - entry_limit) * 2.5), 2)
                color = "red"
            
            st.metric("Precio Actual", f"${current_price:,.2f}")
            st.markdown(f"### Sesgo: :{color}[{bias}]")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Entrada (Limit)", f"${entry_limit:,.2f}")
            col2.metric("Stop Loss (SL)", f"${stop_loss:,.2f}")
            col3.metric("Take Profit (TP)", f"${take_profit:,.2f}")
            
            st.line_chart(df.set_index(pd.to_datetime(df["ts"], unit="ms"))["c"])
