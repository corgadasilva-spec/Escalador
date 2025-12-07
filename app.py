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
        {"nome": "Dra. Ana", "dia": 5, "tipo": "Pedido"},
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
            # Correção de linhas quebradas
            model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] == 2).OnlyEnforceIf(shifts_24h[(m['index'], dia)])
            model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] < 2).OnlyEnforceIf(shifts_24h[(m['index'], dia)].Not())

    # --- REGRAS HARD (Não podem ser quebradas) ---
    
    semanas = {}
    for d_idx, data_obj in enumerate(datas):
        sem_key = data_obj.isocalendar()[:2] 
        if sem_key not in semanas: semanas[sem_key] = []
        semanas[sem_key].append(d_idx + 1)

    for d_idx, data_obj in enumerate(datas):
        dia = d_idx + 1
        is_weekend = data_obj.weekday() >= 5
        
        # 1. Staff Mínimo (A Regra de Ouro)
        model.Add(sum(shifts[(m['index'], dia, 'DIA')] for m in medicos) == num_dia)
        model.Add(sum(shifts[(m['index'], dia, 'NOITE')] for m in medicos) == num_noite)
        
        if is_weekend:
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) == 0)
        else:
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) >= min_manha)

        for m in medicos:
            # Compatibilidade Horária
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'DIA')] <= 1)
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'NOITE')] <= 1)
            
            # BLOQUEIO ABSOLUTO: Férias/CIT/CGS
            if (m['nome'], dia) in hard_ausencias:
                for t in turnos:
                    model.Add(shifts[(m['index'], dia, t)] == 0)

        # Regra FDS '1 Tiro'
        if regra_fds_unico and data_obj.weekday() == 4: # Sexta
            s = dia; sab = dia + 1; dom = dia + 2
            if sab <= num_days and dom <= num_days:
                for m in medicos:
                    sexta_noite = shifts[(m['index'], s, 'NOITE')]
                    sabado_tot = sum(shifts[(m['index'], sab, t)] for t in turnos)
                    domingo_tot = sum(shifts[(m['index'], dom, t)] for t in turnos)
                    model.Add(sexta_noite + sabado_tot + domingo_tot <= 1)

    # Limites Semanais e Descanso
    for m in medicos:
        for sem_key, dias_da_semana in semanas.items():
            model.Add(sum(shifts[(m['index'], d, 'MANHA')] for d in dias_da_semana) <= max_manhas_semana)

        for d_idx in range(len(datas) - 1):
            dia = d_idx + 1
            trabalhou_noite = shifts[(m['index'], dia, 'NOITE')]
            trabalhou_amanha = sum(shifts[(m['index'], dia+1, t)] for t in turnos)
            model.Add(trabalhou_noite + trabalhou_amanha <= 1)

    # --- FUNÇÃO OBJETIVO (Soft Constraints) ---
    obj_terms = []
    
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            
            # A. PENALIZAÇÃO PEDIDO FOLGA
            if (m['nome'], dia) in soft_pedidos:
                trabalha_hoje = sum(shifts[(m['index'], dia, t)] for t in turnos)
                obj_terms.append(trabalha_hoje * -1000)

            # B. BÓNUS PREFERÊNCIA 24h
            if m['pref_24h']:
                obj_terms.append(shifts_24h[(m['index'], dia)] * 50)
            else:
                obj_terms.append(shifts_24h[(m['index'], dia)] * -50)
    
    model.Maximize(sum(obj_terms))

    # --- RESOLVER ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 40.0 
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✅ Escala Gerada! Pedidos analisados.")
        
        dados_grelha = []
        stats = []
        pedidos_recusados = []
        
        fds_cols = [str(d_idx + 1) for d_idx, d in enumerate(datas) if d.weekday() >= 5]

        for m in medicos:
            row = {"Médico": m['nome'], "Eq": m['equipa']}
            n_24h = 0; n_noites = 0; horas_totais = 0
            
            for d_idx, data_obj in enumerate(datas):
                dia = d_idx + 1
                is_dia = solver.Value(shifts[(m['index'], dia, 'DIA')])
                is_noite = solver.Value(shifts[(m['index'], dia, 'NOITE')])
                is_manha = solver.Value(shifts[(m['index'], dia, 'MANHA')])
                
                label = ""
                
                if is_dia and is_noite:
                    label = "DN"; n_24h += 1; horas_totais += 24
                elif is_dia:
                    label = "D"; horas_totais += 12
                elif is_noite:
                    label = "N"; n_noites += 1; horas_totais += 12
                elif is_manha:
                    label = "M"; horas_totais += 6
                
                if label == "":
                    if (m['nome'], dia) in hard_ausencias:
                        tipo = hard_ausencias[(m['nome'], dia)]
                        label = "FER" if tipo == "Férias" else ("CIT" if tipo == "CIT" else "CGS")
                    elif (m['nome'], dia) in soft_pedidos:
                        label = "PED"
                else:
                    if (m['nome'], dia) in soft_pedidos:
                        pedidos_recusados.append(f"{m['nome']} (Dia {dia})")

                row[str(dia)] = label
            
            horas_contrato_mes = m['contrato'] * 4 
            horas_extra = horas_totais - horas_contrato_mes
            
            dados_grelha.append(row)
            stats.append({
                "Médico": m['nome'], 
                "Horas Totais": horas_totais,
                "Horas Extra": horas_extra
            })

        st.subheader(f"Mapa Mensal - {calendar.month_name[mes]} {ano}")
        
        if pedidos_recusados:
            st.warning(f"⚠️ **Pedidos de Folga Recusados:** {', '.join(pedidos_recusados)}")
        else:
            st.success("🎉 Todos os pedidos de folga foram aceites!")

        df_grelha = pd.DataFrame(dados_grelha)
        
        def highlight_cells(val):
            style = ''
            if val == 'DN': style = 'background-color: #ff6666; color: white; font-weight: bold'
            elif val == 'N': style = 'background-color: #66b3ff; color: white'
            elif val == 'D': style = 'background-color: #99ff99; color: black'
            elif val == 'M': style = 'background-color: #ffff99; color: black'
            elif val == 'FER': style = 'background-color: #ffd700; color: black; font-weight: bold'
            elif val == 'CIT': style = 'background-color: #d8bfd8; color: black'
            elif val == 'CGS': style = 'background-color: #a9a9a9; color: white; text-decoration: line-through'
            elif val == 'PED': style = 'background-color: #ccffcc; color: black; border: 2px dashed green'
            return style

        styler = df_grelha.style.applymap(highlight_cells)
        styler.set_properties(subset=fds_cols, **{'border-left': '2px solid #555', 'background-color': '#f8f9fa'})

        st.dataframe(styler, use_container_width=True)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📊 Contadores")
            def color_extra(val):
                return f'color: {"red" if val < 0 else "green"}; font-weight: bold'
            st.dataframe(pd.DataFrame(stats).set_index("Médico").style.applymap(color_extra, subset=['Horas Extra']), use_container_width=True)
            
        with col2:
            st.download_button("📥 Baixar CSV", df_grelha.to_csv().encode('utf-8'), "escala_final.csv")

    else:
        st.error("❌ Erro Crítico: Não há médicos suficientes para cobrir as Hard Constraints.")
