import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date
import calendar

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Gestor Escalas - Real", layout="wide")
st.title("🏥 Gestor de Escalas: Equipas A, B, C, D")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Calendário")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Definição de Vagas")
    num_noite = st.number_input("Nº Médicos Noite", value=3)
    num_dia = st.number_input("Nº Médicos Dia (12h)", value=3)
    num_manha = st.number_input("Nº Médicos Manhã", value=2)
    
    st.divider()
    st.header("⚖️ Regras")
    max_noites_semana = st.number_input("Máx. Noites/Semana", value=2)
    max_turnos_semana = st.number_input("Máx. Turnos/Semana", value=5)
    regra_fds_unico = st.checkbox("🚫 Fim de Semana '1 Tiro'", value=True)

# Calcular dias
num_days = calendar.monthrange(ano, mes)[1]
datas = [date(ano, mes, day) for day in range(1, num_days + 1)]

# ==========================================
# 1. INPUT DE DADOS (DADOS REAIS DA IMAGEM)
# ==========================================
tab_equipa, tab_ausencias = st.tabs(["👥 Equipa Real", "✈️ Ausências"])

with tab_equipa:
    st.info("Lista carregada conforme imagem enviada (Equipas A, B, C, D - 40h).")
    
    # Transcrição da imagem
    # Assumi que os nomes a VERMELHO na imagem preferem 24h
    default_medicos = [
        # EQUIPA A
        {"nome": "Joana Esteves", "equipa": "A", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Andriy Bal", "equipa": "A", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Daniela Alves", "equipa": "A", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "André Colmente", "equipa": "A", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Pedro Moura", "equipa": "A", "contrato": 40, "pref_24h": True, "ativo": True}, # Vermelho
        {"nome": "Miguel Romano", "equipa": "A", "contrato": 40, "pref_24h": True, "ativo": True}, # Vermelho
        
        # EQUIPA B
        {"nome": "Diogo Alves", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Miguel Morgado", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Sérgio Lascasas", "equipa": "B", "contrato": 40, "pref_24h": True, "ativo": True}, # Vermelho
        {"nome": "José Miguel Sá", "equipa": "B", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Joana S. Braga", "equipa": "B", "contrato": 40, "pref_24h": True, "ativo": True}, # Vermelho
        
        # EQUIPA C
        {"nome": "Rogério Silva", "equipa": "C", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Rita Passos", "equipa": "C", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Caldeiro", "equipa": "C", "contrato": 40, "pref_24h": True, "ativo": True}, # Vermelho
        {"nome": "Francisco Silva", "equipa": "C", "contrato": 40, "pref_24h": False, "ativo": True},
        
        # EQUIPA D
        {"nome": "Edite Mendes", "equipa": "D", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Énio Pereira", "equipa": "D", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Vitor Costa", "equipa": "D", "contrato": 40, "pref_24h": True, "ativo": True}, # Vermelho
        {"nome": "Soraia Oliveira", "equipa": "D", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Joana G. Braga", "equipa": "D", "contrato": 40, "pref_24h": False, "ativo": True},
    ]
    
    col_config_med = {
        "pref_24h": st.column_config.CheckboxColumn("Prefere 24h?", default=False),
        "contrato": st.column_config.NumberColumn("H. Contrato", format="%d h", default=40)
    }
    
    df_medicos = st.data_editor(pd.DataFrame(default_medicos), column_config=col_config_med, num_rows="dynamic", use_container_width=True)

with tab_ausencias:
    st.markdown("**Regras:** Férias/CIT bloqueiam dia.")
    default_aus = [{"nome": "Joana Esteves", "dia": 1, "tipo": "Férias"}]
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
if col_act.button("🚀 GERAR ESCALA (EQUIPAS REAIS)", type="primary"):
    
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

    # Variáveis 24h (CÓDIGO SEGURO E CORRIGIDO)
    shifts_24h = {}
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            shifts_24h[(m['index'], dia)] = model.NewBoolVar(f"is_24h_{m['index']}_{dia}")
            
            # Definição segura para evitar erro de sintaxe
            turnos_dia_noite = shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')]
            var_is_24h = shifts_24h[(m['index'], dia)]
            
            # Se a soma for 2 (Dia+Noite), então é 24h
            model.Add(turnos_dia_noite == 2).OnlyEnforceIf(var_is_24h)
            # Se a soma for < 2, não é 24h
            model.Add(turnos_dia_noite < 2).OnlyEnforceIf(var_is_24h.Not())

    # --- REGRAS HARD ---
    for d_idx, data_obj in enumerate(datas):
        dia = d_idx + 1
        is_weekend = data_obj.weekday() >= 5
        
        # Staff
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

    # --- OBJETIVO ---
    obj_terms = []
    
    # 1. FORÇAR PREFERÊNCIA 24h
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            if m['pref_24h']:
                obj_terms.append(shifts_24h[(m['index'], dia)] * 5000) # Prioridade MÁXIMA
            else:
                obj_terms.append(shifts_24h[(m['index'], dia)] * -5000)
            
            if (m['nome'], dia) in soft_pedidos:
                trabalha = sum(shifts[(m['index'], dia, t)] for t in turnos)
                obj_terms.append(trabalha * -10000)

    # 2. Equidade de NOITES (Nivelar)
    total_noites = []
    for m in medicos:
        n = sum(shifts[(m['index'], d+1, 'NOITE')] for d in range(len(datas)))
        v = model.NewIntVar(0, 31, f"n_{m['index']}")
        model.Add(v == n)
        total_noites.append(v)
        
    max_n = model.NewIntVar(0, 31, 'max_n')
    min_n = model.NewIntVar(0, 31, 'min_n')
    model.AddMaxEquality(max_n, total_noites)
    model.AddMinEquality(min_n, total_noites)
    obj_terms.append((max_n - min_n) * -500)

    model.Maximize(sum(obj_terms))

    # --- RESOLVER ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✅ Escala Gerada com Sucesso!")
        
        dados_grelha = []
        stats = []
        pedidos_recusados = []
        fds_cols = [str(d_idx + 1) for d_idx, d in enumerate(datas) if d.weekday() >= 5]
        
        for idx, m in enumerate(medicos):
            row = {"Médico": m['nome'], "Eq": m['equipa']}
            n_24h_real = 0; n_noites_real = 0; horas_totais = 0
            
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
                
                # Labels de ausência
                if label == "":
                    if (m['nome'], dia) in hard_ausencias:
                        tipo = hard_ausencias[(m['nome'], dia)]
                        label = "FER" if tipo == "Férias" else ("CIT" if tipo == "CIT" else "CGS")
                    elif (m['nome'], dia) in soft_pedidos: label = "PED"
                else:
                    if (m['nome'], dia) in soft_pedidos: pedidos_recusados.append(f"{m['nome']} ({dia})")

                row[str(dia)] = label

            contrato_val = m.get('contrato') or 40
            horas_extra = horas_totais - (contrato_val * 4)
            
            dados_grelha.append(row)
            stats.append({
                "Médico": m['nome'], 
                "24h": n_24h_real,
                "Noites Totais": n_noites_real + n_24h_real,
                "Horas Extra": horas_extra
            })

        st.subheader(f"Mapa Mensal - {calendar.month_name[mes]} {ano}")
        if pedidos_recusados: st.warning(f"Pedidos Recusados: {pedidos_recusados}")
        
        df_grelha = pd.DataFrame(dados_grelha)
        
        def highlight_cells(val):
            style = ''
            if val == 'DN': style = 'background-color: #ff4d4d; color: white; font-weight: bold'
            elif val == 'N': style = 'background-color: #4da6ff; color: white'
            elif val == 'D': style = 'background-color: #85e085; color: black'
            elif val == 'M': style = 'background-color: #fff5cc; color: black'
            elif val == 'FER': style = 'background-color: #ffd700; color: black'
            elif val == 'CIT': style = 'background-color: #d8bfd8; color: black'
            elif val == 'PED': style = 'background-color: #ccffcc; color: black; border: 2px dashed green'
            return style

        styler = df_grelha.style.applymap(highlight_cells)
        styler.set_properties(subset=fds_cols, **{'background-color': '#e0e0e0', 'border-left': '2px solid #333', 'border-right': '2px solid #333'})
        st.dataframe(styler, use_container_width=True)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📊 Contadores")
            st.dataframe(pd.DataFrame(stats).set_index("Médico"), use_container_width=True)
        with col2:
            st.download_button("📥 Baixar CSV", df_grelha.to_csv().encode('utf-8'), "escala_real.csv")

    else:
        st.error("❌ Não foi possível gerar. Tente relaxar o 'Máx. Turnos/Semana' na barra lateral.")
