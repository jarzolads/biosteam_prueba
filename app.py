import streamlit as st
import biosteam as bst
import thermosteam as tmo
import google.generativeai as genai
import pandas as pd

# ==========================================
# CONFIGURACIÓN DE GEMINI
# ==========================================
# Es recomendable usar st.secrets para la API Key en producción
API_KEY = "TU_GEMINI_API" 
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# INTERFAZ DE STREAMLIT
# ==========================================
st.set_page_config(page_title="BioSTEAM + Gemini AI", layout="wide")

st.title("👨‍🏫 Simulador Educativo: Separación de Etanol")
st.markdown("### Análisis de Sensibilidad con Inteligencia Artificial")

# Sidebar para parámetros
with st.sidebar:
    st.header("🔧 Parámetros de Proceso")
    f_total = st.number_input("Flujo de alimentación (kg/h)", value=1000)
    z_eth = st.slider("Fracción masa Etanol en entrada", 0.05, 0.15, 0.10)
    t_flash = st.slider("Temperatura de Precalentamiento (°C)", 80, 98, 92)
    p_flash = st.slider("Presión de Operación (atm)", 0.5, 1.5, 1.0)
    
    st.divider()
    analyze_btn = st.button("🚀 Simular y Explicar con IA", type="primary")

# ==========================================
# LÓGICA DE BIOSTEAM (SIMPLIFICADA PARA EL FRONTEND)
# ==========================================
def simular(f, z, t, p):
    chemicals = tmo.Chemicals(['Water', 'Ethanol'])
    bst.settings.set_thermo(chemicals)
    
    # Definición rápida de sistema
    feed = bst.Stream('feed', Water=f*(1-z), Ethanol=f*z, units='kg/hr', T=298.15)
    F1 = bst.Flash('V102', ins=feed, outs=('vapor', 'liquido'), T=t+273.15, P=p*101325)
    
    # Ejecutar
    F1.simulate()
    
    # Resultados clave para la IA
    pureza = F1.outs[0].imass['Ethanol'] / F1.outs[0].F_mass if F1.outs[0].F_mass > 0 else 0
    recuperacion = F1.outs[0].imass['Ethanol'] / feed.imass['Ethanol']
    energia = F1.duty / 3600 # kW
    
    return F1, pureza, recuperacion, energia

# ==========================================
# EJECUCIÓN Y DESPLIEGUE
# ==========================================
if analyze_btn:
    # 1. Correr simulación
    obj_flash, pur, rec, q = simular(f_total, z_eth, t_flash, p_flash)
    
    # 2. Mostrar métricas rápidas
    c1, c2, c3 = st.columns(3)
    c1.metric("Pureza de Etanol (V)", f"{pur:.1%}")
    c2.metric("Recuperación", f"{rec:.1%}")
    c3.metric("Energía Flash", f"{q:.2f} kW")

    # 3. Prompt para Gemini
    # Le damos contexto técnico para que actúe como profesor
    contexto_ia = f"""
    Actúa como un profesor de Ingeniería Química. 
    Se ha simulado un tanque Flash de separación Etanol-Agua con estos datos:
    - Alimentación: {f_total} kg/h con {z_eth:.1%} de etanol.
    - Condiciones: {t_flash}°C y {p_flash} atm.
    - Resultados: Pureza del {pur:.1%} en el vapor y {q:.2f} kW de carga térmica.
    
    Explica de forma concisa por qué estos parámetros dieron ese resultado 
    y qué pasaría con la pureza si aumentamos la presión.
    """

    with st.expander("🤖 Análisis del Profesor Gemini", expanded=True):
        with st.spinner("Gemini está analizando los balances..."):
            response = model.generate_content(contexto_ia)
            st.write(response.text)
    
    # 4. Mostrar Tablas de BioSTEAM
    st.subheader("Datos Detallados de Corrientes")
    df_streams = pd.DataFrame([
        {"Corriente": "Vapor", "Flujo (kg/h)": obj_flash.outs[0].F_mass, "T (°C)": obj_flash.outs[0].T-273.15},
        {"Corriente": "Líquido", "Flujo (kg/h)": obj_flash.outs[1].F_mass, "T (°C)": obj_flash.outs[1].T-273.15}
    ])
    st.dataframe(df_streams)
