import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date, timedelta
import calendar

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Gestão de Escalas - Versão Final", layout="wide")
st.title("🏥 Gestor de Escalas: Regras Semanais vs FDS")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Calendário")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Definição de Vagas")
    num_noite = st.number_input("Nº Médicos Noite (Fixo)", value=3)
    num_dia = st.number_input("Nº Médicos Dia (12h - Fixo)", value=3)
    min_manha = st.number_input("Mín. Manhãs (Só dias úteis)", value=1)
    
    st.divider()
    st.header("⚖️ Regras de Justiça")
    regra_fds_unico = st.checkbox("🚫 Fim de Semana '1 Tiro'", value=True, 
                                  help="Se ativado: Quem faz 6ª Noite, Sábado ou Domingo, NÃO faz mais nada nesse fim de semana.")
    
    permitir_24h = st.checkbox("Permitir turnos 24h (DN)", value=False)

# Calcular dias
num_days = calendar.monthrange(ano, mes)[1]
datas = [date(ano, mes, day) for day in range(1, num_days + 1)]

# ==========================================
# 1. INPUT DE DADOS
# ==========================================
tab_equipa, tab_ausencias = st.tabs(["👥 Equipa & Contratos", "⛔ Ausências"])

with tab_equipa:
    st.markdown("⚠️ **Nota:** A regra '1 turno por FDS' exige uma equipa grande (~18 pax).")
    # Lista de exemplo
    default_medicos = [
        {"nome": "Dr. Silva", "cargo": "ESPECIALISTA", "equipa": "A", "ativo": True},
        {"nome": "Dra. Ana", "cargo": "ESPECIALISTA", "equipa": "B", "ativo": True},
        {"nome": "Dr. Costa", "cargo": "ESPECIALISTA", "equipa": "C", "ativo": True},
        {"nome": "Dr. Ferreira", "cargo": "ESPECIALISTA", "equipa": "A", "ativo": True},
        
        {"nome": "Dr. Pedro", "cargo": "INTERNO_SENIOR", "equipa": "B", "ativo": True},
        {"nome": "Dra. Sofia", "cargo": "INTERNO_SENIOR", "equipa": "C", "ativo": True},
        {"nome": "Dr. Miguel", "cargo": "INTERNO_SENIOR", "equipa": "A", "ativo": True},
        {"nome": "Dra. Joana", "cargo": "INTERNO_SENIOR", "equipa": "B", "ativo": True},
        
        {"nome": "Dr. Rui", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "ativo": True},
        {"nome": "Dra. Marta", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "ativo": True},
        {"nome": "Dr. Tiago", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "ativo": True},
        {"nome": "Dra. Inês", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "ativo": True},
        {"nome": "Dr. Bruno", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "ativo": True},
        
        {"nome": "Dr. Tarefeiro 1", "cargo": "TAREFEIRO", "equipa": "Ext", "ativo": True},
        {"nome": "Dr. Tarefeiro 2", "cargo": "TAREFEIRO", "equipa": "Ext", "ativo": True},
        {"nome": "Dr. Tarefeiro 3", "cargo": "TAREFEIRO", "equipa": "Ext", "ativo": True},
        {"nome": "Dr. Tarefeiro 4", "cargo": "TAREFEIRO", "equipa": "Ext", "ativo": True},
    ]
    df_medicos = st.data_editor(pd.DataFrame(default_medicos), num_rows="dynamic", use_container_width=True)

with tab_ausencias:
    default_aus = [{"nome": "Dr. Silva", "dia": 1}]
    df_ausencias = st.data_editor(pd.DataFrame(default_aus), num_rows="dynamic")

# ==========================================
# 2. MOTOR DE CÁLCULO
# ==========================================
st.divider()
col_act, _ = st.columns([1, 4])
if col_act.button("🚀 GERAR ESCALA", type="primary"):
    
    medicos = df_medicos[df_medicos["ativo"] == True].reset_index().to_dict('records')
    ausencias = {}
    for _, row in df_ausencias.iterrows():
        if row['nome'] not in ausencias: ausencias[row['nome']] = []
        ausencias[row['nome']].append(row['dia'])

    model = cp_model.CpModel()
    shifts = {}
    turnos = ['DIA', 'NOITE', 'MANHA'] 
    
    # Criar Variáveis
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            for t in turnos:
                shifts[(m['index'], dia, t)] = model.NewBoolVar(f"s_{m['index']}_{dia}_{t}")

    # --- REGRAS (HARD CONSTRAINTS) ---
    total_noites = {m['index']: 0 for m in medicos}
    
    for d_idx, data_obj in enumerate(datas):
        dia = d_idx + 1
        is_weekend = data_obj.weekday() >= 5 # 5=Sabado, 6=Domingo
        
        # 1. Quantidades de Staff (DIA e NOITE são fixos)
        model.Add(sum(shifts[(m['index'], dia, 'DIA')] for m in medicos) == num_dia)
        model.Add(sum(shifts[(m['index'], dia, 'NOITE')] for m in medicos) == num_noite)

        # 2. Lógica Específica da MANHÃ (NOVA REGRA!)
        if is_weekend:
            # Fim de Semana: NINGUÉM faz Manhã
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) == 0)
        else:
            # Dias Úteis: Pelo menos X pessoas fazem Manhã
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) >= min_manha)

        # 3. Regras Individuais
        for m in medicos:
            # Imcompatibilidades horárias
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'DIA')] <= 1)
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'NOITE')] <= 1)
            
            if not permitir_24h:
                model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] <= 1)

            # Ausências
            if m['nome'] in ausencias and dia in ausencias[m['nome']]:
                for t in turnos:
                    model.Add(shifts[(m['index'], dia, t)] == 0)

        # 4. Regra Fim de Semana '1 Tiro' (Sexta Noite + Sábado + Domingo <= 1)
        if regra_fds_unico and data_obj.weekday() == 4: # Sexta
            sexta_dia_idx = dia 
            sabado_dia_idx = dia + 1
            domingo_dia_idx = dia + 2
            
            if sabado_dia_idx <= num_days and domingo_dia_idx <= num_days:
                for m in medicos:
                    sexta_noite = shifts[(m['index'], sexta_dia_idx, 'NOITE')]
                    sabado_total = sum(shifts[(m['index'], sabado_dia_idx, t)] for t in turnos)
                    domingo_total = sum(shifts[(m['index'], domingo_dia_idx, t)] for t in turnos)
                    model.Add(sexta_noite + sabado_total + domingo_total <= 1)

    # 5. Descanso e Contagens
    for m in medicos:
        total_noites[m['index']] = sum(shifts[(m['index'], d+1, 'NOITE')] for d in range(len(datas)))
        
        for d_idx in range(len(datas) - 1):
            dia = d_idx + 1
            # Descanso Pós-Noite
            trabalhou_noite = shifts[(m['index'], dia, 'NOITE')]
            trabalhou_amanha = sum(shifts[(m['index'], dia+1, t)] for t in turnos)
            model.Add(trabalhou_noite + trabalhou_amanha <= 1)

    # --- OBJETIVO (Equidade) ---
    max_noites = model.NewIntVar(0, 31, 'max_noites')
    for m in medicos:
        model.Add(total_noites[m['index']] <= max_noites)
    model.Minimize(max_noites)

    # --- RESOLVER ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0 
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✅ Escala Gerada com Sucesso!")
        
        dados_grelha = []
        stats = []

        for m in medicos:
            row = {"Médico": m['nome'], "Eq": m['equipa']}
            n_noites = 0
            n_dias = 0
            n_manhas = 0
            
            for d_idx, data_obj in enumerate(datas):
                dia = d_idx + 1
                is_dia = solver.Value(shifts[(m['index'], dia, 'DIA')])
                is_noite = solver.Value(shifts[(m['index'], dia, 'NOITE')])
                is_manha = solver.Value(shifts[(m['index'], dia, 'MANHA')])
                
                label = ""
                if is_dia and is_noite:
                    label = "DN"
                    n_dias += 1; n_noites += 1
                elif is_dia:
                    label = "D"
                    n_dias += 1
                elif is_noite:
                    label = "N"
                    n_noites += 1
                elif is_manha:
                    label = "M"
                    n_manhas += 1
                
                row[str(dia)] = label
            
            dados_grelha.append(row)
            stats.append({"Médico": m['nome'], "Noites": n_noites, "Dias": n_dias, "Manhãs": n_manhas})

        # GRELHA
        st.subheader(f"Mapa Mensal - {calendar.month_name[mes]} {ano}")
        df_grelha = pd.DataFrame(dados_grelha)
        
        def colorir(val):
            if val == 'DN': return 'background-color: #ff9999; color: black; font-weight: bold' # 24h
            if val == 'N': return 'background-color: #99ccff; color: black' # Noite
            if val == 'D': return 'background-color: #99ff99; color: black' # Dia
            if val == 'M': return 'background-color: #ffff99; color: black' # Manhã
            return ''

        st.dataframe(df_grelha.style.applymap(colorir), use_container_width=True)
        st.dataframe(pd.DataFrame(stats).set_index("Médico"), use_container_width=True)
        
        st.download_button("📥 Baixar CSV", df_grelha.to_csv().encode('utf-8'), "escala.csv")

    else:
        st.error("❌ Impossível gerar escala. Se a regra de FDS estiver ligada, precisa de mais médicos.")
