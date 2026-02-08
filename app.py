import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# ==========================================
# CONFIGURACIÓN DE GEMINI
# ==========================================
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception:
    st.warning("⚠️ No se encontró la API Key de Gemini en Secrets.")

# ==========================================
# INTERFAZ DE STREAMLIT
# ==========================================
st.set_page_config(page_title="Simulador BioSTEAM", layout="wide")
st.title("🧪 Planta de Etanol con Reciclo Energético")

# --- SIDEBAR: PARÁMETROS DINÁMICOS ---
with st.sidebar:
    st.header("⚙️ Parámetros de Control")
    f_mass_total = st.slider("Flujo Alimentación (kg/h)", 500, 2000, 1000)
    t_e100_out = st.slider("Temp. Salida E-100 (°C)", 70, 90, 85)
    t_e101_out = st.slider("Temp. Salida E-101 (°C)", 85, 98, 92)
    p_flash_atm = st.slider("Presión V-102 (atm)", 0.5, 1.5, 1.0)
    
    st.divider()
    btn_simular = st.button("🚀 Ejecutar Simulación e IA", type="primary")

# ==========================================
# LÓGICA DE SIMULACIÓN
# ==========================================
def ejecutar_simulacion(f_total, t_e100, t_e101, p_atm):
    # --- SOLUCIÓN AL ERROR DE ID: Limpiar flowsheet ---
    bst.main_flowsheet.clear() 
    # --------------------------------------------------
    
    # 1. SETUP
    chemicals = tmo.Chemicals(['Water', 'Ethanol'])
    bst.settings.set_thermo(chemicals)
    
    # 2. STREAMS
    f_kmol = f_total / 20.82
    mosto = bst.Stream('mosto_feed', # ID interno único
                       Water=f_kmol*0.9, Ethanol=f_kmol*0.1, units='kmol/hr',
                       T=25 + 273.15, P=101325)

    vinazas_retorno = bst.Stream('vinazas_retorno',
                                 Water=f_kmol*0.9, Ethanol=0, units='kmol/hr',
                                 T=95 + 273.15, P=300000)

    # 3. EQUIPOS
    P100 = bst.Pump('P100', ins=mosto, P=4 * 101325)
    E100 = bst.HXprocess('E100', ins=(P100-0, vinazas_retorno), 
                         outs=('mosto_pre', 'drenaje'), phase0='l', phase1='l')
    E100.outs[0].T = t_e100 + 273.15

    E101 = bst.HXutility('E101', ins=E100-0, T=t_e101 + 273.15)
    V100 = bst.IsenthalpicValve('V100', ins=E101-0, outs='mezcla_bifasica', P=p_atm * 101325)
    V102 = bst.Flash('V102', ins=V100-0, outs=('vapor_caliente', 'vinazas'), P=p_atm * 101325, Q=0)
    E102 = bst.HXutility('E102', ins=V102-0, outs='producto_final', T=25 + 273.15)
    P101 = bst.Pump('P101', ins=V102-1, outs=vinazas_retorno, P=3 * 101325)

    # 4. SISTEMA
    eth_sys = bst.System('eth_sys', path=(P100, E100, E101, V100, V102, E102, P101))
    eth_sys.simulate()
    
    return eth_sys

def generar_reporte_streamlit(sistema):
    datos_mat = []
    for s in sistema.streams:
        if s.F_mass > 0.001:
            datos_mat.append({
                'ID Corriente': s.ID,
                'Temp (°C)': f"{s.T - 273.15:.2f}",
                'Presión (bar)': f"{s.P/1e5:.2f}",
                'Flujo (kg/h)': f"{s.F_mass:.1f}",
                '% Etanol': f"{s.imass['Ethanol']/s.F_mass:.1%}" if s.F_mass > 0 else "0%"
            })
    
    datos_en = []
    for u in sistema.units:
        calor_kw = 0.0
        if hasattr(u, 'heat_utilities') and u.heat_utilities:
            calor_kw = sum(h.duty for h in u.heat_utilities) / 3600
        elif isinstance(u, bst.HXprocess):
            calor_kw = (u.outs[0].H - u.ins[0].H) / 3600

        if abs(calor_kw) > 0.01:
            datos_en.append({'Equipo': u.ID, 'Energía (kW)': round(calor_kw, 2)})
            
    return pd.DataFrame(datos_mat), pd.DataFrame(datos_en)

# --- EJECUCIÓN ---
if btn_simular:
    try:
        with st.spinner("Simulando proceso..."):
            sistema = ejecutar_simulacion(f_mass_total, t_e100_out, t_e101_out, p_flash_atm)
            df_m, df_e = generar_reporte_streamlit(sistema)
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Balance de Materia")
                st.dataframe(df_m, use_container_width=True)
            with col2:
                st.subheader("Requerimientos Energéticos")
                st.dataframe(df_e, use_container_width=True)

            # --- EXPLICACIÓN IA ---
            st.divider()
            st.subheader("🤖 Análisis del Profesor Gemini")
            
            # Recuperar corriente de producto por posición o ID
            prod = sistema.flowsheet.stream.producto_final
            pureza = prod.imass['Ethanol'] / prod.F_mass if prod.F_mass > 0 else 0
            
            prompt = f"""
            Como experto en ingeniería química, analiza estos resultados de BioSTEAM:
            - Temperatura Flash: {t_e101_out}°C.
            - Presión Flash: {p_flash_atm} atm.
            - Pureza de etanol: {pureza:.2%}.
            
            Explica la relación entre la presión y la pureza en este sistema binario.
            """
            
            with st.chat_message("assistant"):
                response = model.generate_content(prompt)
                st.markdown(response.text)
                
    except Exception as e:
        st.error(f"Error en la simulación: {e}")
