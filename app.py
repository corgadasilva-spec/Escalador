import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date
import calendar

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Gestão de Escalas - Pro", layout="wide")
st.title("🏥 Gestor de Escalas: Pedidos vs Obrigações")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Calendário")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Vagas & Regras")
    num_noite = st.number_input("Nº Médicos Noite (Fixo)", value=3)
    num_dia = st.number_input("Nº Médicos Dia (12h - Fixo)", value=3)
    min_manha = st.number_input("Mín. Manhãs (Dias Úteis)", value=1)
    max_manhas_semana = st.number_input("Máx. Manhãs/Semana", value=2)
    
    st.divider()
    usar_equipas = st.checkbox("🛡️ Proteger Equipas (Noites)", value=True)
    regra_fds_unico = st.checkbox("🚫 Fim de Semana '1 Tiro'", value=True)

# Calcular dias
num_days = calendar.monthrange(ano, mes)[1]
datas = [date(ano, mes, day) for day in range(1, num_days + 1)]

# ==========================================
# 1. INPUT DE DADOS
# ==========================================
tab_equipa, tab_ausencias = st.tabs(["👥 Equipa & Preferências", "✈️ Ausências & Pedidos"])

with tab_equipa:
    default_medicos = [
        {"nome": "Dr. Silva", "equipa": "A", "contrato": 36, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Ana", "equipa": "B", "contrato": 36, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Costa", "equipa": "C", "contrato": 36, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Ferreira", "equipa": "A", "contrato": 36, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Beatriz", "equipa": "B", "contrato": 36, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Miguel", "equipa": "A", "contrato": 36, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Pedro", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Sofia", "equipa": "C", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Joana", "equipa": "C", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Rui", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Marta", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Tiago", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Inês", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Bruno", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Tarefeiro 1", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Tarefeiro 2", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Tarefeiro 3", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
    ]
    
    col_config_med = {
        "pref_24h": st.column_config.CheckboxColumn("Prefere 24h?", default=False),
        "contrato": st.column_config.NumberColumn("H. Contrato", format="%d h")
    }
    
    df_medicos = st.data_editor(pd.DataFrame(default_medicos), column_config=col_config_med, num_rows="dynamic", use_container_width=True)

with tab_ausencias:
    st.info("ℹ️ **Férias/CIT/CGS:** Bloqueio Total (Hard). **Pedido:** Tenta dar folga, mas pode escalar se necessário (Soft).")
    
    default_aus = [
        {"nome": "Dr. Silva", "dia": 1, "tipo": "Férias"},
        {"nome": "Dra. Ana", "dia": 5, "tipo": "Pedido"}, # Vamos ver se o sistema aceita ou recusa
    ]
    
    col_config_aus = {
        "tipo": st.column_config.SelectboxColumn("Motivo", options=["Férias", "CIT", "CGS", "Pedido"], required=True),
        "dia": st.column_config.NumberColumn("Dia do Mês", min_value=1, max_value=31)
    }
    
    df_ausencias = st.data_editor(pd.DataFrame(default_aus), column_config=col_config_aus, num_rows="dynamic", use_container_width=True)

# ==========================================
# 2. MOTOR DE CÁLCULO
# ==========================================
st.divider()
col_act, _ = st.columns([1, 4])
if col_act.button("🚀 GERAR ESCALA INTELIGENTE", type="primary"):
    
    medicos = df_medicos[df_medicos["ativo"] == True].reset_index().to_dict('records')
    
    # Separar Hard (Obrigatório) de Soft (Pedido)
    hard_ausencias = {} # (Nome, Dia) -> Tipo
    soft_pedidos = []   # Lista de (Nome, Dia)
    
    for _, row in df_ausencias.iterrows():
        if row['tipo'] in ['Férias', 'CIT', 'CGS']:
            hard_ausencias[(row['nome'], row['dia'])] = row['tipo']
        elif row['tipo'] == 'Pedido':
            soft_pedidos.append((row['nome'], row['dia']))

    model = cp_model.CpModel()
    shifts = {}
    turnos = ['DIA', 'NOITE', 'MANHA']
    
    # Variáveis
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            for t in turnos:
                shifts[(m['index'], dia, t)] = model.NewBoolVar(f"s_{m['index']}_{dia}_{t}")

    # Variáveis 24h (para preferências)
    shifts_24h = {}
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            shifts_24h[(m['index'], dia)] = model.NewBoolVar(f"is_24h_{m['index']}_{dia}")
            model.Add(shifts[(m['index'],
