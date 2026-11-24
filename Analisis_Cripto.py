import streamlit as st
import requests
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Bot de Análisis Técnico OKX", page_icon="📈", layout="centered")

st.title("🤖 Bot de Análisis Técnico para OKX (Futuros y Spot)")
st.markdown("Herramienta analítica con buscador escrito y global para evaluar el sesgo de mercado y niveles operativos (Limit, SL, TP).")

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
            if data["code"] == "0" and len(data["data"]) > 0:
                filtered = [item["instId"] for item in data["data"] if item.get("quoteCcy") == "USDT"]
                symbols.extend(filtered)
                
        if symbols:
            return sorted(list(set(symbols)))
    except Exception:
        pass
    
    return sorted(fallback_symbols)

# Cargar la lista completa de criptomonedas disponibles en OKX
all_symbols = get_okx_all_symbols()

# Barra lateral con buscador escrito e interactivo
st.sidebar.header("Configuración de Mercado")

# 1. Buscador escrito por texto libre
busqueda_texto = st.sidebar.text_input("🔍 Escribe la cripto (ej: PEPE, BTC, SOL)", value="BTC-USDT-SWAP")

# Filtrar la lista según lo que el usuario escriba
busqueda_mayus = busqueda_texto.strip().upper()
simbolos_filtrados = [s for s in all_symbols if busqueda_mayus in s]

# Si el texto escrito coincide con alguno o da resultados, usamos esos; si no, mostramos todos de respaldo
if not simbolos_filtrados:
    simbolos_filtrados = all_symbols

# 2. Selectbox alimentado con el resultado del buscador escrito
symbol = st.sidebar.selectbox(
    "Selecciona el par encontrado", 
    simbolos_filtrados,
    help="Elige de la lista filtrada según lo que escribiste arriba."
)

timeframe = st.sidebar.selectbox("Temporalidad", ["1H", "4H", "1D"], index=1)

# Función para obtener velas históricas de OKX
@st.cache_data(ttl=300)
def get_okx_candles(inst_id, bar, limit=150):
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data["code"] == "0" and len(data["data"]) > 0:
            df = pd.DataFrame(data["data"], columns=["ts", "o", "high", "low", "c", "vol", "volCcy", "volCcyQuote", "confirm"])
            df = df.iloc[::-1].reset_index(drop=True)
            
            df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
            for col in ["o", "high", "low", "c", "vol"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                
            df = df.dropna(subset=["ts", "c", "high", "low"])
            return df
    except Exception:
        pass
    return None

# Botón para ejecutar el análisis
if st.button("🚀 Ejecutar Análisis Técnico"):
    with st.spinner(f"Analizando {symbol} en temporalidad {timeframe}..."):
        df = get_okx_candles(symbol, timeframe)
        
        if df is not None and not df.empty:
            close = df["c"]
            high = df["high"]
            low = df["low"]
            
            # Cálculos técnicos (EMA 50, EMA 200, RSI 14, ATR 14)
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
            
            # Puntuación para determinar sesgo
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
            
            # Mostrar resultados en pantalla
            st.metric("Precio Actual", f"${current_price:,.4f}")
            st.markdown(f"### Sesgo: :{color}[{bias}]")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Entrada (Limit)", f"${entry_limit:,.4f}")
            col2.metric("Stop Loss (SL)", f"${stop_loss:,.4f}")
            col3.metric("Take Profit (TP)", f"${take_profit:,.4f}")
            
            # Gráfico protegido
            try:
                chart_data = df.copy()
                chart_data["date"] = pd.to_datetime(chart_data["ts"], unit="ms", errors="coerce")
                chart_data = chart_data.dropna(subset=["date"])
                st.line_chart(chart_data.set_index("date")["c"])
            except Exception:
                st.line_chart(df["c"])
        else:
            st.error("No se pudieron obtener datos válidos para este activo en OKX.")
