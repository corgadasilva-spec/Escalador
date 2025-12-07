import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date
import calendar

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Gestor Escalas - Versão Final 24h", layout="wide")
st.title("🏥 Gestor de Escalas: Prioridade 24h & Equidade")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Calendário")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Staff (Regra dos 3)")
    num_noite = st.number_input("Nº Médicos Noite", value=3)
    num_dia = st.number_input("Nº Médicos Dia (12h)", value=3)
    num_manha = st.number_input("Nº Médicos Manhã", value=3)
    
    st.divider()
    st.header("⚖️ Limites de Segurança")
    max_noites_semana = st.number_input("Máx. Noites/Semana", value=2)
    max_turnos_semana = st.number_input("Máx. Turnos/Semana (DN=2)", value=5)
    regra_fds_unico = st.checkbox("🚫 Fim de Semana '1 Tiro'", value=True)

# Calcular dias
num_days = calendar.monthrange(ano, mes)[1]
datas = [date(ano, mes, day) for day in range(1, num_days + 1)]

# ==========================================
# 1. INPUT DE DADOS
# ==========================================
tab_equipa, tab_ausencias = st.tabs(["👥 Equipa (Quem quer 24h?)", "✈️ Ausências"])

with tab_equipa:
    st.markdown("**Instrução:** Marque a caixa `Prefere 24h` para quem deve fazer D+N seguido.")
    default_medicos = [
        {"nome": "Dr. Silva", "equipa": "A", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Ana", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Costa", "equipa": "C", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Ferreira", "equipa": "A", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Beatriz", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Miguel", "equipa": "A", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Pedro", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Sofia", "equipa": "C", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Joana", "equipa": "C", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Rui", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Marta", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Tiago", "equipa": "Rot", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dra. Inês", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Bruno", "equipa": "Rot", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Lucas", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Carla", "equipa": "Rot", "contrato": 40, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Tarefeiro 1", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Tarefeiro 2", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Tarefeiro 3", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
        {"nome": "Dr. Tarefeiro 4", "equipa": "Ext", "contrato": 0, "pref_24h": True, "ativo": True},
    ]
    
    col_config_med = {
        "pref_24h": st.column_config.CheckboxColumn("Prefere 24h?", default=False),
        "contrato": st.column_config.NumberColumn("H. Contrato", format="%d h", default=0)
    }
    
    df_medicos = st.data_editor(pd.DataFrame(default_medicos), column_config=col_config_med, num_rows="dynamic", use_container_width=True)

with tab_ausencias:
    default_aus = [{"nome": "Dr. Silva", "dia": 1, "tipo": "Férias"}]
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
if col_act.button("🚀 GERAR ESCALA (PRIORIDADE 24H)", type="primary"):
    
    # 1. Preparação
    medicos = df_medicos[df_medicos["ativo"] == True].reset_index().to_dict('records')
    hard_ausencias = {} 
    soft_pedidos = []   
    
    for _, row in df_ausencias.iterrows():
        if row['tipo'] in ['Férias', 'CIT', 'CGS']:
            hard_ausencias[(row['nome'], row['dia'])] = row['tipo']
        elif row['tipo'] == 'Pedido':
            soft_pedidos.append((row['nome'], row['dia']))

    model = cp_model.CpModel()
    shifts = {}
    turnos = ['DIA', 'NOITE', 'MANHA']
    
    # 2. Variáveis de Decisão
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            for t in turnos:
                shifts[(m['index'], dia, t)] = model.NewBoolVar(f"s_{m['index']}_{dia}_{t}")

    # Variáveis Auxiliares 24h - CÓDIGO SEGURO
    shifts_24h = {}
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            shifts_24h[(m['index'], dia)] = model.NewBoolVar(f"is_24h_{m['index']}_{dia}")
            
            # Atalhos para evitar linhas longas
            t_dia = shifts[(m['index'], dia, 'DIA')]
            t_noite = shifts[(m['index'], dia, 'NOITE')]
            var_24h = shifts_24h[(m['index'], dia)]
            
            # Lógica corrigida e partida em linhas menores
            model.Add(t_dia + t_noite == 2).OnlyEnforceIf(var_24h)
            model.Add(t_dia + t_noite < 2).OnlyEnforceIf(var_24h.Not())

    # --- REGRAS HARD ---
    for d_idx, data_obj in enumerate(datas):
        dia = d_idx + 1
        is_weekend = data_obj.weekday() >= 5
        
        # Staff Mínimo
        model.Add(sum(shifts[(m['index'], dia, 'DIA')] for m in medicos) == num_dia)
        model.Add(sum(shifts[(m['index'], dia, 'NOITE')] for m in medicos) == num_noite)
        
        if is_weekend:
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) == 0)
        else:
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) == num_manha)

        for m in medicos:
            # Incompatibilidades
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'DIA')] <= 1)
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'NOITE')] <= 1)
            
            # Ausências
            if (m['nome'], dia) in hard_ausencias:
                for t in turnos:
                    model.Add(shifts[(m['index'], dia, t)] == 0)

        # FDS '1 Tiro'
        if regra_fds_unico and data_obj.weekday() == 4: # Sexta
            s = dia; sab = dia + 1; dom = dia + 2
            if sab <= num_days and dom <= num_days:
                for m in medicos:
                    sexta_noite = shifts[(m['index'], s, 'NOITE')]
                    sabado_tot = sum(shifts[(m['index'], sab, t)] for t in turnos)
                    domingo_tot = sum(shifts[(m['index'], dom, t)] for t in turnos)
                    model.Add(sexta_noite + sabado_tot + domingo_tot <= 1)

    # --- JANELAS DE DESCANSO ---
    for m in medicos:
        for d_idx in range(len(datas) - 1):
            dia = d_idx + 1
            # Descanso Pós-Noite
            trabalhou_noite = shifts[(m['index'], dia, 'NOITE')]
            trabalhou_amanha = sum(shifts[(m['index'], dia+1, t)] for t in turnos)
            model.Add(trabalhou_noite + trabalhou_amanha <= 1)

        # Máx Noites / Semana
        for d_idx in range(len(datas) - 6):
            noites_janela = sum(shifts[(m['index'], d_idx + k + 1, 'NOITE')] for k in range(7))
            model.Add(noites_janela <= max_noites_semana)

        # Máx Turnos / Semana
        for d_idx in range(len(datas) - 6):
            turnos_janela = sum(shifts[(m['index'], d_idx + k + 1, t)] for k in range(7) for t in turnos)
            model.Add(turnos_janela <= max_turnos_semana)

    # --- OBJETIVO: PESOS E EQUIDADE ---
    total_noites_medico = []
    total_fds_medico = []
    
    # Contadores
    for m in medicos:
        # Noites
        n_noites = sum(shifts[(m['index'], d+1, 'NOITE')] for d in range(len(datas)))
        n_var = model.NewIntVar(0, 31, f"n_noites_{m['index']}")
        model.Add(n_var == n_noites)
        total_noites_medico.append(n_var)
        
        # FDS
        fds_vars = []
        for d_idx in range(len(datas)):
            if datas[d_idx].weekday() == 5: # Sábado
                sab_idx = d_idx; dom_idx = d_idx + 1
                if dom_idx < len(datas):
                    t_sab = sum(shifts[(m['index'], sab_idx+1, t)] for t in turnos)
                    t_dom = sum(shifts[(m['index'], dom_idx+1, t)] for t in turnos)
                    trab_fds = t_sab + t_dom
                    
                    touched = model.NewBoolVar(f"fds_{m['index']}_{sab_idx}")
                    model.Add(trab_fds > 0).OnlyEnforceIf(touched)
                    model.Add(trab_fds == 0).OnlyEnforceIf(touched.Not())
                    fds_vars.append(touched)
        if fds_vars:
            n_fds = sum(fds_vars)
            f_var = model.NewIntVar(0, 5, f"n_fds_{m['index']}")
            model.Add(f_var == n_fds)
            total_fds_medico.append(f_var)

    obj_terms = []

    # 1. FORÇAR PREFERÊNCIA 24h
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            if m['pref_24h']:
                obj_terms.append(shifts_24h[(m['index'], dia)] * 2000)
            else:
                obj_terms.append(shifts_24h[(m['index'], dia)] * -2000)
            
            if (m['nome'], dia) in soft_pedidos:
                trabalha = sum(shifts[(m['index'], dia, t)] for t in turnos)
                obj_terms.append(trabalha * -5000)

    # 2. Equidade de NOITES
    max_noites = model.NewIntVar(0, 31, 'max_noites')
    min_noites = model.NewIntVar(0, 31, 'min_noites')
    model.AddMaxEquality(max_noites, total_noites_medico)
    model.AddMinEquality(min_noites, total_noites_medico)
    obj_terms.append((max_noites - min_noites) * -500)

    # 3. Equidade de FDS
    if total_fds_medico:
        max_fds = model.NewIntVar(0, 5, 'max_fds')
        min_fds = model.NewIntVar(0, 5, 'min_fds')
        model.AddMaxEquality(max_fds, total_fds_medico)
        model.AddMinEquality(min_fds, total_fds_medico)
        obj_terms.append((max_fds - min_fds) * -500)

    model.Maximize(sum(obj_terms))

    # --- RESOLVER ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✅ Escala Gerada! Preferências 24h aplicadas com força.")
        
        dados_grelha = []
        stats = []
        pedidos_recusados = []
        fds_cols = [str(d_idx + 1) for d_idx, d in enumerate(datas) if d.weekday() >= 5]
        
        for idx, m in enumerate(medicos):
            row = {"Médico": m['nome'], "Eq": m['equipa']}
            n_24h_real = 0; n_noites_real = 0
            
            horas_totais = 0
            for d_idx, _ in enumerate(datas):
                dia = d_idx + 1
                is_dia = solver.Value(shifts[(m['index'], dia, 'DIA')])
                is_noite = solver.Value(shifts[(m['index'], dia, 'NOITE')])
                is_manha = solver.Value(shifts[(m['index'], dia, 'MANHA')])
                
                label = ""
                if is_dia and is_noite: label = "DN"; n_24h_real += 1; horas_totais += 24
                elif is_dia: label = "D"; horas_totais += 12
                elif is_noite: label = "N"; n_noites_real += 1; horas_totais += 12
                elif is_manha: label = "M"; horas_totais += 6
                
                if label == "":
                    if (m['nome'], dia) in hard_ausencias:
                        tipo = hard_ausencias[(m['nome'], dia)]
                        label = "FER" if tipo == "Férias" else ("CIT" if tipo == "CIT" else "CGS")
                    elif (m['nome'], dia) in soft_pedidos: label = "PED"
                else
