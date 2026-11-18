import streamlit as st
import requests
import pandas as pd
import ccxt

# Configuración de la página
st.set_page_config(page_title="Bot de Trading Automático OKX", page_icon="📈", layout="centered")

st.title("🤖 Bot de Análisis y Ejecución Automática en OKX")
st.markdown("Herramienta avanzada para evaluar el sesgo de mercado, calcular niveles y **ejecutar órdenes reales o en modo demo**.")

# --- BARRA LATERAL: CREDENCIALES Y CONFIGURACIÓN ---
st.sidebar.header("🔑 Credenciales API de OKX")
api_key = st.sidebar.text_input("API Key", type="password")
secret_key = st.sidebar.text_input("Secret Key", type="password")
password = st.sidebar.text_input("Passphrase", type="password")

use_testnet = st.sidebar.checkbox("Activar Modo Demo / Testnet", value=True)
execute_trade_auto = st.sidebar.checkbox("⚠️ Habilitar Ejecución Automática de Órdenes", value=False)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuración de Riesgo")
capital_to_risk = st.sidebar.number_input("Capital a arriesgar por operación (USDT)", value=10.0, min_value=1.0)

# Función para obtener dinámicamente los futuros / swaps en USDT de OKX con respaldo seguro
@st.cache_data(ttl=3600)
def get_okx_futures_symbols():
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("code") == "0":
            symbols = [item["instId"] for item in data.get("data", []) if item.get("quoteCcy") == "USDT"]
            if symbols:
                return sorted(symbols)
    except Exception:
        pass
    
    # Lista de respaldo robusta en caso de que la API falle o no devuelva datos
    return sorted([
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
        "BNB-USDT-SWAP", "DOGE-USDT-SWAP", "ADA-USDT-SWAP", "AVAX-USDT-SWAP",
        "LINK-USDT-SWAP", "SUI-USDT-SWAP", "PEPE-USDT-SWAP", "SHIB-USDT-SWAP",
        "NEAR-USDT-SWAP", "MATIC-USDT-SWAP", "DOT-USDT-SWAP", "LTC-USDT-SWAP"
    ])

all_symbols = get_okx_futures_symbols()

st.sidebar.header("Mercado")
default_index = all_symbols.index("BTC-USDT-SWAP") if "BTC-USDT-SWAP" in all_symbols else 0
symbol = st.sidebar.selectbox("🔍 Criptomoneda (Futuros)", all_symbols, index=default_index, help="Escribe para buscar cualquier cripto")
timeframe = st.sidebar.selectbox("Temporalidad", ["1H", "4H", "1D"], index=1)

# Función para obtener velas históricas de OKX
@st.cache_data(ttl=300)
def get_okx_candles(inst_id, bar, limit=150):
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    if data.get("code") == "0":
        df = pd.DataFrame(data["data"], columns=["ts", "o", "high", "low", "c", "vol", "volCcy", "volCcyQuote", "confirm"])
        df = df.iloc[::-1].reset_index(drop=True)
        for col in ["o", "high", "low", "c", "vol"]:
            df[col] = pd.to_numeric(df[col])
        return df
    else:
        st.error("Error al conectar con la API de OKX para este símbolo.")
        return None

# Función para ejecutar la orden en OKX usando CCXT
def execute_order_on_okx(symbol, side, entry_price, stop_loss, take_profit, amount_usdt, api_key, secret_key, password, testnet):
    try:
        exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': secret_key,
            'password': password,
            'enableRateLimit': True,
        })
        
        if testnet:
            exchange.set_sandbox_mode(True)
            
        amount = round(amount_usdt / entry_price, 4)
        if amount <= 0:
            amount = 1.0

        order = exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=entry_price
        )
        
        st.success(f"✅ ¡Orden Limit ejecutada con éxito en OKX! ID: {order['id']}")
        
    except Exception as e:
        st.error(f"❌ Error al conectar o ejecutar en OKX: {str(e)}")

# Botón para ejecutar el análisis y opcionalmente el trade
if st.button("🚀 Ejecutar Análisis y Evaluar Operativa"):
    with st.spinner(f"Analizando {symbol} en temporalidad {timeframe}..."):
        df = get_okx_candles(symbol, timeframe)
        
        if df is not None and not df.empty:
            close = df["c"]
            high = df["high"]
            low = df["low"]
            
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
            
            score = 0
            if current_price > ema_50: score += 1
            if ema_50 > ema_200: score += 2
            if rsi < 30: score += 1
            elif rsi > 70: score -= 1
            
            if score > 0:
                bias = "ALCISTA (Mayor probabilidad de Subida)"
                side = "buy"
                entry_limit = round(recent_low + (atr * 0.3), 4)
                stop_loss = round(entry_limit - (atr * 1.5), 4)
                take_profit = round(entry_limit + ((entry_limit - stop_loss) * 2.5), 4)
                color = "green"
            else:
                bias = "BAJISTA (Mayor probabilidad de Bajada)"
                side = "sell"
                entry_limit = round(recent_high - (atr * 0.3), 4)
                stop_loss = round(entry_limit + (atr * 1.5), 4)
                take_profit = round(entry_limit - ((stop_loss - entry_limit) * 2.5), 4)
                color = "red"
            
            st.metric("Precio Actual del Futuro", f"${current_price:,.4f}")
            st.markdown(f"### Sesgo: :{color}[{bias}]")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Entrada (Limit)", f"${entry_limit:,.4f}")
            col2.metric("Stop Loss (SL)", f"${stop_loss:,.4f}")
            col3.metric("Take Profit (TP)", f"${take_profit:,.4f}")
            
            st.line_chart(df.set_index(pd.to_datetime(df["ts"], unit="ms"))["c"])
            
            if execute_trade_auto:
                if not api_key or not secret_key or not password:
                    st.warning("⚠️ Has activado la ejecución automática, pero faltan tus credenciales API de OKX en la barra lateral.")
                else:
                    st.info("🔄 Enviando orden automática a OKX...")
                    execute_order_on_okx(
                        symbol=symbol,
                        side=side,
                        entry_price=entry_limit,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        amount_usdt=capital_to_risk,
                        api_key=api_key,
                        secret_key=secret_key,
                        password=password,
                        testnet=use_testnet
                    )
