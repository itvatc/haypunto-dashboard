import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import plotly.express as px
import json
import os

# 1. Configuración de la interfaz web
st.set_page_config(
    page_title="HaypuntoLive - Acceso Privado",
    page_icon="🔒",
    layout="wide"
)

# 2. Diccionario de Usuarios Autorizados
USUARIOS_AUTORIZADOS = {
    "admin": "haypunto2026",
    "gerencia": "cobranzas2026",
    "coordinador": "pos2026",
    "jtovar": "jtovar2026*",
    "ymeza": "ymeza2026*"
}

# 3. Control de Estado de Sesión (Login)
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "usuario_actual" not in st.session_state:
    st.session_state["usuario_actual"] = ""

def validar_login():
    user = st.session_state["input_usuario"].strip().lower()
    passw = st.session_state["input_password"].strip()
    
    if user in USUARIOS_AUTORIZADOS and USUARIOS_AUTORIZADOS[user] == passw:
        st.session_state["autenticado"] = True
        st.session_state["usuario_actual"] = user
    else:
        st.error("❌ Usuario o contraseña incorrectos.")

# --- PANTALLA DE LOGIN ---
if not st.session_state["autenticado"]:
    st.title("🔒 Acceso Restringido - HaypuntoLive")
    st.subheader("Ingresa tus credenciales para ver el Panel de Control")
    
    col_login, _ = st.columns([1, 2])
    with col_login:
        st.text_input("Usuario", key="input_usuario")
        st.text_input("Contraseña", type="password", key="input_password")
        st.button("🔑 Iniciar Sesión", on_click=validar_login)
    
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.success(f"👤 Conectado como: **{st.session_state['usuario_actual'].upper()}**")
if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state["autenticado"] = False
    st.rerun()

# --- 4. CONEXIÓN A FIREBASE Y DASHBOARD ---
@st.cache_resource
def inicializar_firebase():
    if not firebase_admin._apps:
        if os.path.exists("firebase_key.json"):
            cred = credentials.Certificate("firebase_key.json")
            return firebase_admin.initialize_app(cred)
        try:
            if "firebase" in st.secrets:
                key_dict = json.loads(st.secrets["firebase"])
                cred = credentials.Certificate(key_dict)
                return firebase_admin.initialize_app(cred)
        except Exception:
            pass
        return None
    return firebase_admin.get_app()

app = inicializar_firebase()
if app is None:
    st.error("⚠️ No se encontró 'firebase_key.json'.")
    st.stop()

db = firestore.client()

@st.cache_data(ttl=30)
def obtener_metricas_completas():
    try:
        docs_historial = db.collection("historial_notificaciones").stream()
        registros = []
        for doc in docs_historial:
            data = doc.to_dict()
            fecha_raw = data.get("fecha_hora")
            registros.append({
                "Serial POS": data.get("serial", "DESCONOCIDO").strip().upper(),
                "RIF Cliente": data.get("rif", "---").strip().upper(),
                "Estado Alerta": data.get("tipo_notificacion", "SIN CLASIFICAR"),
                "Fecha / Hora": fecha_raw.strftime("%Y-%m-%d %H:%M:%S") if fecha_raw else "Sin Fecha",
                "_fecha_obj": fecha_raw
            })
        return pd.DataFrame(registros), None
    except Exception as e:
        return pd.DataFrame(), str(e)

# Encabezado principal
st.title("📡 Panel de Control: Notificaciones y Sincronización POS")
st.caption("Acceso privado para Auditoría y Gerencia de HaypuntoLive")

if st.button("🔄 Refrescar Indicadores"):
    st.cache_data.clear()

df_raw, error_msg = obtener_metricas_completas()

if error_msg:
    st.error(f"❌ Error al consultar Firestore: {error_msg}")
    st.stop()

if not df_raw.empty:
    df_raw = df_raw.sort_values(by="_fecha_obj", ascending=False)
    conteo_impactos = df_raw.groupby("Serial POS").size().to_dict()
    
    df_equipos = df_raw.drop_duplicates(subset=["Serial POS"], keep="first").copy()
    df_equipos["Total Notificaciones"] = df_equipos["Serial POS"].map(conteo_impactos)
    df_equipos.rename(columns={"Fecha / Hora": "Última Notificación"}, inplace=True)

    # Selector dinámico de modo para los gráficos
    modo_vista = st.radio(
        "📊 **Selecciona la perspectiva de cálculo para las gráficas:**",
        ["Total de Disparos Acumulados (Todos los eventos)", "Equipos Físicos Únicos (1 por POS)"],
        horizontal=True
    )

    # Determinamos qué DataFrame alimentar a los gráficos
    df_graficos = df_raw if "Total" in modo_vista else df_equipos

    # Bloque de KPIs
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("📱 Equipos Únicos", len(df_equipos))
    k2.metric("🔔 Total Disparos", len(df_raw))
    k3.metric("🟢 Al Día", len(df_graficos[df_graficos["Estado Alerta"] == "AL DIA"]))
    k4.metric("⚠️ Deuda Leve", len(df_graficos[df_graficos["Estado Alerta"] == "AVISO DEUDA LEVE"]))
    k5.metric("🚨 Mora Alta", len(df_graficos[df_graficos["Estado Alerta"] == "ALERTA DEUDA GRAVE"]))

    st.markdown("---")

    # BLOQUE DE GRÁFICOS
    col_graf1, col_graf2 = st.columns(2)

    with col_graf1:
        st.subheader("Proporción por Estado de Cuenta")
        fig_pie = px.pie(
            df_graficos,
            names="Estado Alerta",
            color="Estado Alerta",
            color_discrete_map={
                "AL DIA": "#2ECC71",
                "AVISO DEUDA LEVE": "#F1C40F",
                "ALERTA DEUDA GRAVE": "#E74C3C"
            },
            hole=0.45
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_graf2:
        st.subheader("Volumen por Tipo de Notificación")
        conteo_df = df_graficos["Estado Alerta"].value_counts().reset_index()
        conteo_df.columns = ["Estado Alerta", "Cantidad"]
        fig_bar = px.bar(
            conteo_df,
            x="Estado Alerta",
            y="Cantidad",
            color="Estado Alerta",
            color_discrete_map={
                "AL DIA": "#2ECC71",
                "AVISO DEUDA LEVE": "#F1C40F",
                "ALERTA DEUDA GRAVE": "#E74C3C"
            },
            text="Cantidad"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # Bloque de Tabla de Auditoría
    st.subheader("📋 Auditoría por Serial POS")
    busqueda = st.text_input("🔍 Buscar por Serial o RIF:")
    df_tabla = df_equipos.drop(columns=["_fecha_obj"], errors="ignore")
    if busqueda:
        df_tabla = df_tabla[
            df_tabla["Serial POS"].str.contains(busqueda.upper()) |
            df_tabla["RIF Cliente"].str.contains(busqueda.upper())
        ]
    st.dataframe(df_tabla, use_container_width=True, height=350)
else:
    st.info("ℹ️ No hay eventos registrados aún en 'historial_notificaciones'.")
