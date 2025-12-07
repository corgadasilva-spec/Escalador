import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date
import calendar

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Gestor Escalas - Equidade Total", layout="wide")
st.title("🏥 Gestor de Escalas: Equidade & Distribuição Justa")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Calendário")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Regras de Staff (Tudo a 3)")
    # Defaults alterados para 3 conforme pedido "todos os turnos têm de ter 3 médicos"
    num_noite = st.number_input("Nº Médicos Noite", value=3)
    num_dia = st.number_input("Nº Médicos Dia (12h)", value=3)
    num_manha = st.number_input("Nº Médicos Manhã (Reforço)", value=3)
    
    st.divider()
    st.header("⚖️ Regras de Justiça")
    max_manhas_semana = st.number_input("Máx. Manhãs/Semana por médico", value=2)
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
    st.info("💡 Dica: Para cobrir 3 pessoas em TODOS os turnos (D+N+M = 9 turnos/dia), precisa de uma equipa grande (~20+ médicos).")
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
        {"nome": "Dr. Tiago", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Inês", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Bruno", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dr. Lucas", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
        {"nome": "Dra. Carla", "equipa": "Rot", "contrato": 40, "pref_24h": False, "ativo": True},
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
    st.markdown("**Regras:** Férias/CIT bloqueiam. Pedidos tentam ser aceites.")
    default_aus = [
        {"nome": "Dr. Silva", "dia": 1, "tipo": "Férias"},
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
if col_act.button("🚀 GERAR ESCALA EQUITATIVA", type="primary"):
    
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

    # Variáveis Auxiliares (24h)
    shifts_24h = {}
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            shifts_24h[(m['index'], dia)] = model.NewBoolVar(f"is_24h_{m['index']}_{dia}")
            # Correção de sintaxe
            model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] == 2).OnlyEnforceIf(shifts_24h[(m['index'], dia)])
            model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] < 2).OnlyEnforceIf(shifts_24h[(m['index'], dia)].Not())

    # --- REGRAS HARD (OBRIGATÓRIAS) ---
    
    semanas = {}
    for d_idx, data_obj in enumerate(datas):
        sem_key = data_obj.isocalendar()[:2] 
        if sem_key not in semanas: semanas[sem_key] = []
        semanas[sem_key].append(d_idx + 1)

    for d_idx, data_obj in enumerate(datas):
        dia = d_idx + 1
        is_weekend = data_obj.weekday() >= 5
        
        # 1. STAFF MÍNIMO (Regra: Todos os turnos têm 3 médicos, ou o definido)
        model.Add(sum(shifts[(m['index'], dia, 'DIA')] for m in medicos) == num_dia)
        model.Add(sum(shifts[(m['index'], dia, 'NOITE')] for m in medicos) == num_noite)
        
        # Manhã: Se for FDS é 0, se for semana é o número definido (ex: 3)
        if is_weekend:
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) == 0)
        else:
            model.Add(sum(shifts[(m['index'], dia, 'MANHA')] for m in medicos) == num_manha)

        for m in medicos:
            # Incompatibilidades
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'DIA')] <= 1)
            model.Add(shifts[(m['index'], dia, 'MANHA')] + shifts[(m['index'], dia, 'NOITE')] <= 1)
            
            # Ausências Hard
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

    # --- MOTOR DE EQUIDADE (SOFT CONSTRAINTS) ---
    # Aqui criamos variáveis para contar o total de horas de cada médico
    # E dizemos ao Solver para minimizar a diferença entre o Max e o Min.
    
    total_horas_medico = []
    
    for m in medicos:
        # Calcular horas deste médico no mês inteiro
        horas_var = model.NewIntVar(0, 300, f"horas_{m['index']}")
        
        # Soma ponderada: Manhã=6, Dia=12, Noite=12
        turnos_pesados = []
        for d_idx in range(len(datas)):
            dia = d_idx + 1
            turnos_pesados.append(shifts[(m['index'], dia, 'MANHA')] * 6)
            turnos_pesados.append(shifts[(m['index'], dia, 'DIA')] * 12)
            turnos_pesados.append(shifts[(m['index'], dia, 'NOITE')] * 12)
        
        model.Add(horas_var == sum(turnos_pesados))
        total_horas_medico.append(horas_var)

    # Variáveis para encontrar o Máximo e Mínimo de horas na equipa
    max_horas_equipa = model.NewIntVar(0, 300, 'max_horas')
    min_horas_equipa = model.NewIntVar(0, 300, 'min_horas')
    
    model.AddMaxEquality(max_horas_equipa, total_horas_medico)
    model.AddMinEquality(min_horas_equipa, total_horas_medico)

    # --- OBJETIVO FINAL ---
    obj_terms = []

    # 1. EQUIDADE (Prioridade Máxima): Minimizar (Max - Min)
    # Multiplicamos por 200 para ser mais importante que preferências individuais
    distancia_equidade = model.NewIntVar(0, 300, 'distancia')
    model.Add(distancia_equidade == max_horas_equipa - min_horas_equipa)
    obj_terms.append(distancia_equidade * -200) 

    # 2. Preferências Individuais
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            # Pedido Folga (Soft)
            if (m['nome'], dia) in soft_pedidos:
                trabalha = sum(shifts[(m['index'], dia, t)] for t in turnos)
                obj_terms.append(trabalha * -1000) # Penalização gigante se recusar

            # Preferência 24h
            if m['pref_24h']:
                obj_terms.append(shifts_24h[(m['index'], dia)] * 50)
            else:
                obj_terms.append(shifts_24h[(m['index'], dia)] * -50)

    model.Maximize(sum(obj_terms))

    # --- RESOLVER ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0 # Mais tempo para calcular equidade
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✅ Escala Equitativa Gerada!")
        
        dados_grelha = []
        stats = []
        pedidos_recusados = []
        
        # Identificar colunas de Fim de Semana para o Styler
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
            
            # Correção do contrato None -> 0
            contrato_val = m.get('contrato')
            if contrato_val is None: contrato_val = 0
            
            horas_contrato_mes = contrato_val * 4 
            horas_extra = horas_totais - horas_contrato_mes
            
            dados_grelha.append(row)
            stats.append({
                "Médico": m['nome'], 
                "Horas Totais": horas_totais,
                "Horas Extra": horas_extra,
                "Noites": n_noites + n_24h
            })

        st.subheader(f"Mapa Mensal - {calendar.month_name[mes]} {ano}")
        
        if pedidos_recusados:
            st.warning(f"⚠️ **Pedidos Recusados:** {', '.join(pedidos_recusados)}")

        df_grelha = pd.DataFrame(dados_grelha)
        
        # --- STYLING AVANÇADO ---
        def highlight_cells(val):
            style = ''
            if val == 'DN': style = 'background-color: #ff4d4d; color: white; font-weight: bold' # Vermelho forte
            elif val == 'N': style = 'background-color: #4da6ff; color: white' # Azul forte
            elif val == 'D': style = 'background-color: #85e085; color: black' # Verde
            elif val == 'M': style = 'background-color: #fff5cc; color: black' # Amarelo
            elif val == 'FER': style = 'background-color: #ffd700; color: black; font-weight: bold'
            elif val == 'CIT': style = 'background-color: #d8bfd8; color: black'
            elif val == 'CGS': style = 'background-color: #a9a9a9; color: white; text-decoration: line-through'
            elif val == 'PED': style = 'background-color: #ccffcc; color: black; border: 2px dashed green'
            return style

        styler = df_grelha.style.applymap(highlight_cells)
        
        # Destacar Fins de Semana com cinzento escuro e borda
        # Nota: O Pandas Styler pode variar dependendo da versão, mas isto funciona na maioria.
        styler.set_properties(subset=fds_cols, **{
            'background-color': '#e0e0e0', # Cinzento mais escuro
            'border-left': '2px solid #333',
            'border-right': '2px solid #333',
            'font-weight': 'bold'
        })

        st.dataframe(styler, use_container_width=True)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("⚖️ Análise de Equidade")
            df_stats = pd.DataFrame(stats).set_index("Médico")
            
            # Calcular o desvio para mostrar quão justa é a escala
            media_horas = df_stats['Horas Totais'].mean()
            df_stats['Desvio da Média'] = df_stats['Horas Totais'] - media_horas
            
            def color_desvio(val):
                # Se desvio for pequeno (-6 a +6h), é verde (ótimo)
                if abs(val) <= 6: return 'color: green; font-weight: bold'
                # Se for grande, vermelho
                return 'color: red; font-weight: bold'

            st.dataframe(df_stats.style.applymap(color_desvio, subset=['Desvio da Média']), use_container_width=True)
            
        with col2:
            st.info("Legenda:\n- **Colunas Cinzentas**: Fins de Semana\n- **Desvio**: Diferença entre as horas do médico e a média da equipa.")
            st.download_button("📥 Baixar CSV", df_grelha.to_csv().encode('utf-8'), "escala_equitativa.csv")

    else:
        st.error("❌ Impossível gerar escala. Causa provável: Regras de Staff muito altas (3 em tudo) para o nº de médicos disponíveis.")
        st.warning("Tente adicionar mais médicos na tabela ou reduzir os requisitos de 'Manhã' na barra lateral.")
