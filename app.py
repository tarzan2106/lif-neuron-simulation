import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import subprocess
import random

# =====================================================================
# CONFIGURAÇÃO DA PÁGINA
# =====================================================================
st.set_page_config(page_title="SNN Lab EDA", page_icon="⚡", layout="wide")

# =====================================================================
# FUNÇÃO AUXILIAR: Traduz sufixos SPICE para float
# =====================================================================
def spice_to_float(valor_str):
    valor_str = str(valor_str).lower().strip()
    if valor_str.endswith('p'): return float(valor_str[:-1]) * 1e-12
    if valor_str.endswith('n'): return float(valor_str[:-1]) * 1e-9
    if valor_str.endswith('u'): return float(valor_str[:-1]) * 1e-6
    if valor_str.endswith('m'): return float(valor_str[:-1]) * 1e-3
    try: return float(valor_str)
    except ValueError: return 0.0

# =====================================================================
# ESTADO DA SESSÃO (Memória)
# =====================================================================
if 'lista_de_pulsos' not in st.session_state:
    st.session_state.lista_de_pulsos = []

# =====================================================================
# BARRA LATERAL
# =====================================================================
with st.sidebar:
    st.header("🎛️ Parametrização dos pulsos de entrada")
    
    tab_det, tab_estoc = st.tabs(["🎯 Pulsos exatos", "🎲 Pulsos estocásticos"])
    
    with tab_det:
        st.subheader("Gerador de pulsos exatos")
        n_det = st.number_input("Quantidade de pulsos", min_value=1, value=1, step=1, key="n_det")
        amp_det = st.text_input("Amplitude (ex: 60u)", value="60u", key="amp_det")
        larg_det = st.text_input("Largura (ex: 10n)", value="10n", key="larg_det")
        atraso_det = st.text_input("Espaçamento entre os pulsos (ex: 5n)", value="5n", key="atraso_det")
        
        if st.button("➕ Adicionar pulsos ao sinal de entrada", key="btn_add_exato", use_container_width=True, type="primary"):
            if amp_det and larg_det and atraso_det:
                for _ in range(n_det):
                    st.session_state.lista_de_pulsos.append({
                        "Tipo": "Exato", "Amplitude": amp_det, "Largura": larg_det, "Espaçamento": atraso_det
                    })
                st.rerun() 
            else:
                st.error("Preencha todos os campos!")

    with tab_estoc:
        st.subheader("Gerador de pulsos estocásticos")
        n_estoc = st.number_input("Quantidade de pulsos", min_value=1, value=100, step=10, key="n_estoc")
        larg_estoc = st.text_input("Largura (ex: 10n)", value="10n")
        espaco_estoc = st.text_input("Espaçamento médio entre os pulsos (Exponencial) (ex: 50n)", value="50n")
        
        tipo_dist = st.radio("Distribuição da amplitude", ["Uniforme (Min/Max)", "Gaussiana (Média/Std)"])
        
        if tipo_dist == "Uniforme (Min/Max)":
            col1, col2 = st.columns(2)
            vmin_estoc = col1.text_input("Min", value="40u")
            vmax_estoc = col2.text_input("Max", value="80u")
        else:
            col1, col2 = st.columns(2)
            vmed_estoc = col1.text_input("Média", value="60u")
            vstd_estoc = col2.text_input("Desvio", value="15u")
            
        if st.button("➕ Adicionar pulsos ao sinal de entrada", key="btn_add_estocastico", use_container_width=True, type="primary"):
            espaco_medio = spice_to_float(espaco_estoc)
            if espaco_medio > 0:
                for _ in range(n_estoc):
                    atraso_aleatorio = random.expovariate(1.0 / espaco_medio)
                    
                    if tipo_dist == "Uniforme (Min/Max)":
                        vmin, vmax = spice_to_float(vmin_estoc), spice_to_float(vmax_estoc)
                        amp_aleatoria = random.uniform(vmin, vmax)
                    else:
                        vmed, vstd = spice_to_float(vmed_estoc), spice_to_float(vstd_estoc)
                        amp_aleatoria = random.gauss(vmed, vstd)
                        if amp_aleatoria < 0: amp_aleatoria = 0.0
                    
                    amp_form = f"{amp_aleatoria * 1e6:.2f}u"
                    atraso_form = f"{atraso_aleatorio * 1e9:.2f}n"
                    
                    st.session_state.lista_de_pulsos.append({
                        "Tipo": "Aleatório", "Amplitude": amp_form, "Largura": larg_estoc, "Espaçamento": atraso_form
                    })
                st.rerun()

# =====================================================================
# PAINEL PRINCIPAL
# =====================================================================
st.title("⚡ Resposta de um neurônio LIF")
st.markdown("Análise da resposta de um neurônio LIF sob pulsos de correntes arbitrários na entrada utilizando skywater130 e o ngspice como simulador.")

aba_simulador, aba_esquematico = st.tabs(["🚀 Simulador", "📐 Esquemático e Parâmetros"])

# ---------------------------------------------------------------------
# ABA 2: ESQUEMÁTICO E PARÂMETROS
# ---------------------------------------------------------------------
with aba_esquematico:
    st.header("Arquitetura do Neurônio LIF")
    
    # Diagrama Visual (Renderizado nativamente pelo Streamlit)
    st.markdown("""
    ```mermaid
    graph LR
        In((I_in)) --> Mem[Nó da Membrana]
        Mem --- C_mem[(C_mem)]
        Mem --- Leak[Leak NMOS]
        Mem --> ST[Schmitt Trigger]
        ST --> U2[Inv Saída]
        ST --> U1[Inv Reset]
        U1 --> Rst[Reset NMOS]
        Rst -.->|Aterra| Mem
        U2 --> Out((Spike Out))
        Out --- C_load[(C_load)]