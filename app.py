"""
================================================================================
ECOTECHO IoT - TENDEDERO INTELIGENTE - DASHBOARD
PROGRAMA SENATIC 2026 - IEM ARTEMIO MENDOZA
Sensores:  Lluvia (FC-37), Temperatura y Humedad (DHT22), Luz (LDR)
Actuador:  Servomotor que lleva la ropa bajo el techo
Flujo:     Wokwi (ESP32) -> ThingSpeak -> GitHub -> Streamlit
================================================================================
"""

import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ============================================================================
# 1. CONFIGURACION DE LA PAGINA
# ============================================================================
st.set_page_config(
    page_title="EcoTecho IoT",
    page_icon="☂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# 2. CREDENCIALES THINGSPEAK (Settings -> Secrets en Streamlit)
# ============================================================================
try:
    API_KEY = st.secrets["THINGSPEAK_READ_KEY"]
    CHANNEL_ID = st.secrets["THINGSPEAK_CHANNEL_ID"]
except Exception:
    API_KEY = ""            # canal publico: puede quedar vacio
    CHANNEL_ID = "1234567"  # reemplazar por el Channel ID real

CAMPOS = {
    "field1": "Temperatura",
    "field2": "Humedad",
    "field3": "Lluvia",
    "field4": "Luz",
    "field5": "BajoTecho",
    "field6": "Motivo",
    "field7": "Recogidas",
    "field8": "Secado",
}
NUMERICAS = list(CAMPOS.values())
MOTIVOS = {0: "Normal", 1: "Lluvia", 2: "Noche", 3: "Humedad alta"}

PAG_INICIO = "🏠 Inicio"
PAG_GRAFICAS = "📈 Gráficas históricas"
PAG_TENDEDERO = "👕 Tendedero"
PAG_ALARMAS = "🔔 Alarmas"
PAG_CLIMA = "🌦️ Clima y secado"
PAG_DESCARGAS = "📥 Descargas"


# ============================================================================
# 3. FUNCIONES AUXILIARES
# ============================================================================
@st.cache_data(ttl=20)
def obtener_datos(num_puntos=100):
    """Descarga las ultimas lecturas del canal de ThingSpeak."""
    url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    params = {"results": num_puntos}
    if API_KEY:
        params["api_key"] = API_KEY
    try:
        respuesta = requests.get(url, params=params, timeout=10)
        respuesta.raise_for_status()
        feeds = respuesta.json().get("feeds", [])
    except Exception as e:
        st.error(f"No se pudo conectar con ThingSpeak: {e}")
        return None

    if not feeds:
        return pd.DataFrame()

    df = pd.DataFrame(feeds).rename(columns=CAMPOS)
    df["created_at"] = pd.to_datetime(df["created_at"]).dt.tz_convert("America/Bogota")
    for col in NUMERICAS:
        if col not in df:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["Temperatura", "Humedad"]).reset_index(drop=True)


def crear_gauge(valor, minimo, maximo, titulo, unidad, zonas):
    """Indicador semicircular con zonas de color."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=valor,
        title={"text": titulo, "font": {"size": 18}},
        number={"suffix": unidad, "font": {"size": 40}},
        gauge={
            "axis": {"range": [minimo, maximo], "tickwidth": 1},
            "bar": {"color": "#1d4f73", "thickness": 0.7},
            "steps": zonas,
        },
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=60, b=20))
    return fig


def texto_posicion(valor):
    return "BAJO TECHO" if valor == 1 else "AL SOL"


def texto_motivo(valor):
    return MOTIVOS.get(int(valor), "Desconocido") if pd.notna(valor) else "Sin dato"


def verificar_alarmas(ultima):
    """Revisa la ultima lectura."""
    alertas = []
    ll, pos = ultima["Lluvia"], ultima["BajoTecho"]
    h, t, sec = ultima["Humedad"], ultima["Temperatura"], ultima["Secado"]

    if pd.notna(ll) and ll >= 30 and pos != 1:
        alertas.append(("CRITICA", f"Está lloviendo ({ll:.0f} %) y la ropa sigue afuera: revisar el mecanismo"))
    elif pd.notna(ll) and ll >= 30:
        alertas.append(("INFO", f"Lloviendo ({ll:.0f} %). La ropa está protegida bajo techo"))
    if pd.notna(h) and h > 90:
        alertas.append(("MEDIA", f"Humedad muy alta ({h:.0f} %): la ropa secará lento"))
    if pd.notna(t) and t < 5:
        alertas.append(("MEDIA", f"Temperatura muy baja ({t:.1f} °C)"))
    if pd.notna(sec) and sec < 30 and pos != 1:
        alertas.append(("MEDIA", f"Índice de secado bajo ({sec:.0f}/100) con la ropa al sol"))
    return alertas


# ============================================================================
# 4. SIDEBAR - NAVEGACION
# ============================================================================
with st.sidebar:
    st.markdown(
        """
        <div style='text-align:center; padding:16px 0;'>
            <div style='font-size:40px;'>☂️</div>
            <div style='font-weight:bold; font-size:18px;'>EcoTecho IoT</div>
            <div style='font-size:12px; color:gray;'>Tu ropa segura, sin importar el clima</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")
    pagina = st.radio(
        "Navegación",
        [PAG_INICIO, PAG_GRAFICAS, PAG_TENDEDERO, PAG_ALARMAS, PAG_CLIMA, PAG_DESCARGAS],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.subheader("⚙️ Configuración")
    num_puntos = st.slider("Lecturas a mostrar", 10, 500, 100, 10)
    auto_refresh = st.checkbox("⚡ Actualizar cada 20 s", value=False)
    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ============================================================================
# 5. CARGAR DATOS
# ============================================================================
df = obtener_datos(num_puntos)

if df is None or df.empty:
    st.error("❌ No hay datos. Verifique el Channel ID, la Read API Key y que Wokwi esté enviando.")
    st.stop()

ultima = df.iloc[-1]
anterior = df.iloc[-2] if len(df) > 1 else ultima

# ============================================================================
# 6. PAGINA: INICIO
# ============================================================================
if pagina == PAG_INICIO:
    st.markdown("# ☂️ EcoTecho IoT · Tendedero inteligente")
    st.markdown("Estado del tendedero y del clima en el patio.")
    st.caption(f"Última lectura: {ultima['created_at'].strftime('%Y-%m-%d %H:%M:%S')} (hora Colombia)")

    if ultima["BajoTecho"] == 1:
        st.info(f"🏠 La ropa está **BAJO TECHO** · motivo: {texto_motivo(ultima['Motivo'])}")
    else:
        st.success("☀️ La ropa está **AL SOL**, secándose")

    st.markdown("### 📊 Sensores")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lluvia (%)", f"{ultima['Lluvia']:.0f}", f"{ultima['Lluvia'] - anterior['Lluvia']:+.0f}",
              delta_color="inverse")
    c2.metric("Temperatura (°C)", f"{ultima['Temperatura']:.1f}",
              f"{ultima['Temperatura'] - anterior['Temperatura']:+.1f}")
    c3.metric("Humedad (%)", f"{ultima['Humedad']:.1f}",
              f"{ultima['Humedad'] - anterior['Humedad']:+.1f}", delta_color="inverse")
    c4.metric("Luz (%)", f"{ultima['Luz']:.0f}", f"{ultima['Luz'] - anterior['Luz']:+.0f}")

    c5, c6 = st.columns(2)
    c5.metric("Índice de secado (0-100)", f"{ultima['Secado']:.0f}")
    c6.metric("Recogidas desde el encendido", f"{ultima['Recogidas']:.0f}")

    st.markdown("---")
    criticas = [a for a in verificar_alarmas(ultima) if a[0] == "CRITICA"]
    if criticas:
        st.error(f"🚨 {criticas[0][1]}")
    else:
        st.success("✅ Sistema funcionando correctamente")

# ============================================================================
# 7. PAGINA: GRAFICAS HISTORICAS
# ============================================================================
elif pagina == PAG_GRAFICAS:
    st.markdown("# 📈 Gráficas históricas")
    st.markdown("Tendencia de lluvia, luz, temperatura, humedad e índice de secado.")

    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=("Lluvia (%)", "Luz (%)", "Temperatura (°C)", "Humedad (%)",
                        "Índice de secado", ""),
        vertical_spacing=0.12,
    )
    series = [
        ("Lluvia", "#1d6fa5", 1, 1),
        ("Luz", "#c08a00", 1, 2),
        ("Temperatura", "#c2410c", 2, 1),
        ("Humedad", "#0e7490", 2, 2),
        ("Secado", "#3f8f4f", 3, 1),
    ]
    for col, color, fila, columna in series:
        fig.add_trace(
            go.Scatter(x=df["created_at"], y=df[col], name=col, line=dict(color=color, width=2)),
            row=fila, col=columna,
        )
    fig.update_layout(height=900, showlegend=False, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# 8. PAGINA: TENDEDERO
# ============================================================================
elif pagina == PAG_TENDEDERO:
    st.markdown("# 👕 Tendedero")
    st.markdown("Cuándo estuvo la ropa al sol, cuándo bajo techo y por qué.")

    tiempo_sol = (df["BajoTecho"] == 0).mean() * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("Posición actual", texto_posicion(ultima["BajoTecho"]))
    c2.metric("Motivo", texto_motivo(ultima["Motivo"]))
    c3.metric("Tiempo al sol (periodo mostrado)", f"{tiempo_sol:.0f} %")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df["created_at"], y=df["Lluvia"], name="Lluvia (%)",
                             fill="tozeroy", line=dict(color="#1d6fa5", width=1)),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df["created_at"], y=df["BajoTecho"], name="Bajo techo",
                             line_shape="hv", line=dict(color="#c2410c", width=3)),
                  secondary_y=True)
    fig.update_yaxes(title_text="Lluvia (%)", range=[0, 100], secondary_y=False)
    fig.update_yaxes(tickvals=[0, 1], ticktext=["Al sol", "Bajo techo"], range=[-0.1, 1.2],
                     secondary_y=True)
    fig.update_layout(height=420, template="plotly_white", hovermode="x unified",
                      legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Motivos de recogida")
    conteo = (df[df["BajoTecho"] == 1]["Motivo"].map(texto_motivo)
              .value_counts().rename_axis("Motivo").reset_index(name="Lecturas"))
    if conteo.empty:
        st.info("En este periodo la ropa no se ha recogido.")
    else:
        st.dataframe(conteo, use_container_width=True, hide_index=True)

# ============================================================================
# 9. PAGINA: ALARMAS
# ============================================================================
elif pagina == PAG_ALARMAS:
    st.markdown("# 🔔 Centro de alarmas")
    alertas = verificar_alarmas(ultima)
    if alertas:
        for tipo, mensaje in alertas:
            if tipo == "CRITICA":
                st.error(f"🚨 {mensaje}")
            elif tipo == "MEDIA":
                st.warning(f"⚠️ {mensaje}")
            else:
                st.info(f"ℹ️ {mensaje}")
    else:
        st.success("✅ No hay alarmas activas.")

    st.markdown("### 📋 Reglas configuradas")
    st.dataframe(pd.DataFrame({
        "Condición": ["Lluvia ≥ 30 % y ropa afuera", "Lluvia ≥ 30 % y ropa bajo techo",
                      "Humedad > 90 %", "Temperatura < 5 °C", "Secado < 30 con ropa al sol"],
        "Severidad": ["CRÍTICA", "INFORMATIVA", "MEDIA", "MEDIA", "MEDIA"],
    }), use_container_width=True, hide_index=True)

# ============================================================================
# 10. PAGINA: CLIMA Y SECADO
# ============================================================================
elif pagina == PAG_CLIMA:
    st.markdown("# 🌦️ Clima y secado")
    st.markdown("Qué tan buenas son las condiciones para secar la ropa en este momento.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.plotly_chart(crear_gauge(
            ultima["Secado"], 0, 100, "Índice de secado", "",
            [{"range": [0, 30], "color": "#fecaca"},
             {"range": [30, 60], "color": "#fef3c7"},
             {"range": [60, 100], "color": "#bbf7d0"}],
        ), use_container_width=True)
    with c2:
        st.plotly_chart(crear_gauge(
            ultima["Temperatura"], 0, 35, "Temperatura", " °C",
            [{"range": [0, 10], "color": "#bfdbfe"},
             {"range": [10, 20], "color": "#fef3c7"},
             {"range": [20, 35], "color": "#bbf7d0"}],
        ), use_container_width=True)
    with c3:
        st.plotly_chart(crear_gauge(
            ultima["Humedad"], 0, 100, "Humedad", " %",
            [{"range": [0, 60], "color": "#bbf7d0"},
             {"range": [60, 85], "color": "#fef3c7"},
             {"range": [85, 100], "color": "#fecaca"}],
        ), use_container_width=True)

    st.caption("El índice de secado lo calcula el ESP32 con temperatura, humedad y luz. "
               "Vale 0 cuando llueve. Es una estimación para comparar momentos del día.")

# ============================================================================
# 11. PAGINA: DESCARGAS
# ============================================================================
elif pagina == PAG_DESCARGAS:
    st.markdown("# 📥 Descarga de datos")

    df_export = df[["created_at"] + NUMERICAS].copy()
    df_export["created_at"] = df_export["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df_export["Motivo"] = df_export["Motivo"].map(texto_motivo)
    df_export = df_export.rename(columns={"created_at": "Fecha_Hora"})
    hoy = datetime.now().strftime("%Y%m%d")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("📄 CSV", df_export.to_csv(index=False).encode("utf-8"),
                           f"ecotecho_{hoy}.csv", "text/csv", use_container_width=True)
    with c2:
        st.download_button("📋 JSON", df_export.to_json(orient="records").encode("utf-8"),
                           f"ecotecho_{hoy}.json", "application/json", use_container_width=True)
    with c3:
        st.markdown(f"**{len(df_export)} registros** disponibles")

    st.markdown("### 📋 Vista previa")
    st.dataframe(df_export.sort_values("Fecha_Hora", ascending=False),
                 use_container_width=True, hide_index=True)

# ============================================================================
# 12. PIE DE PAGINA
# ============================================================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align:center; color:gray; font-size:12px;'>
        <p>☂️ EcoTecho IoT · PROGRAMA SENATIC 2026 - IEM ARTEMIO MENDOZA</p>
        <p>ESP32 + Sensor de lluvia + DHT22 + LDR + Servomotor → ThingSpeak → GitHub → Streamlit</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# 13. ACTUALIZACION AUTOMATICA
# ============================================================================
if auto_refresh:
    time.sleep(20)
    st.cache_data.clear()
    st.rerun()
