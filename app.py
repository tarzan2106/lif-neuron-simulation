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
# FUNÇÃO AUXILIAR: Traduz sufixos SPICE para float matemático
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
# ESTADO DA SESSÃO (A memória da nossa ferramenta)
# =====================================================================
if 'lista_de_pulsos' not in st.session_state:
    st.session_state.lista_de_pulsos = []

# =====================================================================
# BARRA LATERAL (PAINEL DE CONTROLE)
# =====================================================================
with st.sidebar:
    st.header("🎛️ Parâmetros de Entrada")
    
    tab_det, tab_estoc = st.tabs(["🎯 Exato", "🎲 Ruído (Poisson)"])
    
    # --- ABA 1: SINAIS DETERMINÍSTICOS ---
    with tab_det:
        st.subheader("Gerador de Trens de Pulso")
        n_det = st.number_input("Quantidade (N)", min_value=1, value=1, step=1, key="n_det")
        amp_det = st.text_input("Amplitude (ex: 60u)", value="60u", key="amp_det")
        larg_det = st.text_input("Largura (ex: 10n)", value="10n", key="larg_det")
        atraso_det = st.text_input("Atraso/Espaço (ex: 5n)", value="5n", key="atraso_det")
        
        if st.button("➕ Adicionar Exato", use_container_width=True):
            if amp_det and larg_det and atraso_det:
                for _ in range(n_det):
                    st.session_state.lista_de_pulsos.append({
                        "Tipo": "Exato", "Amplitude": amp_det, "Largura": larg_det, "Espaçamento": atraso_det
                    })
                st.rerun() 
            else:
                st.error("Preencha todos os campos!")

    # --- ABA 2: SINAIS ESTOCÁSTICOS ---
    with tab_estoc:
        st.subheader("Gerador de Ruído Biológico")
        n_estoc = st.number_input("Quantidade de Pulsos", min_value=1, value=100, step=10)
        larg_estoc = st.text_input("Largura Fixa (ex: 10n)", value="10n")
        espaco_estoc = st.text_input("Espaçamento Médio (ex: 50n)", value="50n")
        
        tipo_dist = st.radio("Distribuição de Amplitude", ["Uniforme (Min/Max)", "Gaussiana (Média/Std)"])
        
        if tipo_dist == "Uniforme (Min/Max)":
            col1, col2 = st.columns(2)
            vmin_estoc = col1.text_input("Min", value="40u")
            vmax_estoc = col2.text_input("Max", value="80u")
        else:
            col1, col2 = st.columns(2)
            vmed_estoc = col1.text_input("Média", value="60u")
            vstd_estoc = col2.text_input("Desvio", value="15u")
            
        if st.button("➕ Adicionar Aleatório", use_container_width=True, type="primary"):
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
# PAINEL PRINCIPAL (CENTRO DA TELA)
# =====================================================================
st.title("⚡ SNN Lab: Gerador de Padrões & Simulador LIF")
st.markdown("Validação no nível do silício (SkyWater 130nm PDK) com injeção parametrizada de estímulos e ruído de rede.")

# --- 1. A Fila de Memória ---
if not st.session_state.lista_de_pulsos:
    st.info("👈 Use o painel lateral para configurar e adicionar pulsos ao circuito.")
else:
    st.subheader("🛒 Fila de Estímulos (Memória)")
    
    df_pulsos = pd.DataFrame(st.session_state.lista_de_pulsos)
    df_pulsos.index += 1 
    st.dataframe(df_pulsos, use_container_width=True, height=200)
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🗑️ Limpar Fila", use_container_width=True):
            st.session_state.lista_de_pulsos.clear()
            st.rerun()

    # --- 2. O Cérebro do SPICE e Botão de Execução ---
    st.divider()
    
    if st.button("🚀 RODAR SIMULAÇÃO SPICE", type="primary", use_container_width=True):
        with st.spinner('A compilar a Netlist e a resolver matrizes SPICE...'):
            
            # --- Tradução Matemática ---
            pwl_pontos = ["0 0"]
            t_absoluto = 0.0
            t_rise = 1e-12 
            menor_largura = float('inf')

            for p in st.session_state.lista_de_pulsos:
                amp = spice_to_float(p["Amplitude"])
                largura = spice_to_float(p["Largura"])
                atraso = spice_to_float(p["Espaçamento"])
                
                if largura < menor_largura: menor_largura = largura

                t0 = t_absoluto + atraso
                t1 = t0 + t_rise
                t2 = t1 + largura
                t3 = t2 + t_rise

                pwl_pontos.append(f"{t0:.12e} 0")
                pwl_pontos.append(f"{t1:.12e} {amp}")
                pwl_pontos.append(f"{t2:.12e} {amp}")
                pwl_pontos.append(f"{t3:.12e} 0")
                
                t_absoluto = t3

            tempo_total = t_absoluto + 50e-9 
            passo_sim = min(menor_largura / 5.0, 1e-9)
            if passo_sim > menor_largura / 2.0: passo_sim = menor_largura / 2.0

            pwl_linhas = []
            for i in range(0, len(pwl_pontos), 4):
                pwl_linhas.append(" ".join(pwl_pontos[i:i+4]))
            pwl_string = "\n+ ".join(pwl_linhas)

            pdk_path = "PDKs/sky130_fd_pr/models/corners/tt_lite.spice"
            c_mem = "300f"
            
            # --- Netlist ---
            netlist_content = f"""* SNN: LIF - Tool Web App

.include {pdk_path}

.subckt MEU_INVERSOR in out vdd gnd
X_P1 out in vdd vdd sky130_fd_pr__pfet_01v8 W=10.0 L=0.15
X_N1 out in gnd gnd sky130_fd_pr__nfet_01v8 W=10.0 L=0.15
.ends MEU_INVERSOR

.subckt MEU_SCHMITT_TRIGGER in out vdd gnd
X_P1 net_p in vdd vdd sky130_fd_pr__pfet_01v8 W=10.0 L=0.15
X_P2 out in net_p vdd sky130_fd_pr__pfet_01v8 W=10.0 L=0.15
X_P3 net_p out gnd vdd sky130_fd_pr__pfet_01v8 W=10.0 L=0.15
X_N1 out in net_n gnd sky130_fd_pr__nfet_01v8 W=10.0 L=0.15
X_N2 net_n in gnd gnd sky130_fd_pr__nfet_01v8 W=10.0 L=0.15
X_N3 net_n out vdd gnd sky130_fd_pr__nfet_01v8 W=10.0 L=0.15
.ends MEU_SCHMITT_TRIGGER

.subckt NEURONIO_LIF in_corrente spike_out vdd gnd vlk vwidth
C_mem in_corrente gnd {c_mem}
X_leak in_corrente vlk gnd gnd sky130_fd_pr__nfet_01v8 W=10.0 L=0.15
X_ST in_corrente vo_node vdd gnd MEU_SCHMITT_TRIGGER
X_U2 vo_node spike_out vdd gnd MEU_INVERSOR
X_U1 vo_node reset_ctrl vwidth gnd MEU_INVERSOR
X_reset in_corrente reset_ctrl gnd gnd sky130_fd_pr__nfet_01v8 W=10.0 L=0.15
.ends NEURONIO_LIF

V_vdd vdd_node 0 1.0
V_vlk vlk_node 0 0.5
V_vwidth vwidth_node 0 0.9

I_in 0 no_fonte PWL({pwl_string})
V_amperimetro no_fonte in_node 0V
X_MEU_LIF in_node out_node vdd_node 0 vlk_node vwidth_node NEURONIO_LIF

.control
tran {passo_sim:.6e} {tempo_total:.6e}
wrdata workspace/dados_gui.txt i(V_amperimetro) v(in_node) v(out_node)
quit
.endc
.end
"""
            workspace_dir = "workspace"
            os.makedirs(workspace_dir, exist_ok=True)
            netlist_path = os.path.join(workspace_dir, "neuronio_gui.cir")
            data_path = os.path.join(workspace_dir, "dados_gui.txt")

            with open(netlist_path, "w") as file:
                file.write(netlist_content)

            # --- Execução do SPICE ---
            try:
                subprocess.run(["ngspice", "-b", netlist_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                st.error("Erro: O NGSpice não foi encontrado no PATH do sistema.")
                st.stop()

            # --- Leitura de Dados ---
            tempos_us, i_entrada, v_membrana, v_saida = [], [], [], []
            try:
                with open(data_path, "r") as f:
                    for linha in f:
                        if not linha.strip(): continue
                        colunas = [float(val) for val in linha.split()]
                        tempos_us.append(colunas[0] * 1e6) # Microssegundos 
                        i_entrada.append(colunas[1] * 1e6) # Microamperes
                        v_membrana.append(colunas[3])
                        v_saida.append(colunas[5])
            except FileNotFoundError:
                st.error("Falha ao ler os dados do SPICE.")
                st.stop()

            # --- 3. Renderização com PLOTLY (Gráficos Interativos) ---
            st.success(f"Simulação concluída! Foram processados {len(st.session_state.lista_de_pulsos)} estímulos.")
            
            # Criamos as Abas Visuais
            tab_junto, tab_separado = st.tabs(["📉 Gráfico Sobreposto", "📊 Gráficos Separados"])
            
            # -----------------------------------------------------------------
            # VISUALIZAÇÃO 1: SOBREPOSTO (EIXO DUPLO)
            # -----------------------------------------------------------------
            with tab_junto:
                fig_junto = make_subplots(specs=[[{"secondary_y": True}]])

                fig_junto.add_trace(go.Scatter(x=tempos_us, y=v_membrana, mode='lines', name='Vm (V)',
                                         line=dict(color='orange', width=2)), secondary_y=False)
                
                fig_junto.add_trace(go.Scatter(x=tempos_us, y=v_saida, mode='lines', name='Spike (V)',
                                         line=dict(color='green', width=2)), secondary_y=False)
                
                # Modificado: Corrente com linha contínua, azul mais claro (dodgerblue) e leve transparência
                fig_junto.add_trace(go.Scatter(x=tempos_us, y=i_entrada, mode='lines', name='Corrente (µA)',
                                         line=dict(color='dodgerblue', width=2), opacity=0.6), secondary_y=True)

                fig_junto.update_layout(
                    title="Análise Sobreposta de Transientes (Clique nos nomes da legenda para ocultar curvas)",
                    xaxis_title="Tempo (µs)",
                    hovermode="x unified",
                    height=500,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )

                fig_junto.update_yaxes(title_text="Tensão (V)", range=[-0.1, 1.2], secondary_y=False)
                fig_junto.update_yaxes(title_text="Corrente (µA)", secondary_y=True)

                st.plotly_chart(fig_junto, use_container_width=True)
            
            # -----------------------------------------------------------------
            # VISUALIZAÇÃO 2: SEPARADOS (SUBPLOTS EM CASCATA)
            # -----------------------------------------------------------------
            with tab_separado:
                # Criamos um gráfico com 3 linhas (uma para cada grandeza) com eixo X compartilhado
                fig_sep = make_subplots(
                    rows=3, cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.08,
                    subplot_titles=("Corrente de Entrada", "Tensão de Membrana", "Spike de Saída")
                )
                
                # Curva 1
                fig_sep.add_trace(go.Scatter(x=tempos_us, y=i_entrada, mode='lines', name='Corrente (µA)',
                                         line=dict(color='dodgerblue', width=2)), row=1, col=1)
                # Curva 2
                fig_sep.add_trace(go.Scatter(x=tempos_us, y=v_membrana, mode='lines', name='Vm (V)',
                                         line=dict(color='orange', width=2)), row=2, col=1)
                # Curva 3
                fig_sep.add_trace(go.Scatter(x=tempos_us, y=v_saida, mode='lines', name='Spike (V)',
                                         line=dict(color='green', width=2)), row=3, col=1)
                
                fig_sep.update_layout(
                    height=700, 
                    hovermode="x unified",
                    showlegend=False # A legenda aqui foi desligada porque os títulos dos subplots já explicam
                )
                
                # Ajustando limites e labels de cada eixo Y
                fig_sep.update_yaxes(title_text="I (µA)", row=1, col=1)
                fig_sep.update_yaxes(title_text="Tensão (V)", range=[-0.1, 1.2], row=2, col=1)
                fig_sep.update_yaxes(title_text="Tensão (V)", range=[-0.1, 1.2], row=3, col=1)
                
                fig_sep.update_xaxes(title_text="Tempo (µs)", row=3, col=1)
                
                st.plotly_chart(fig_sep, use_container_width=True)