import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date
import calendar

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Gestor Escalas - Equidade Granular", layout="wide")
st.title("🏥 Gestor de Escalas: Distribuição Perfeita")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📅 Calendário")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Staff")
    num_noite = st.number_input("Nº Médicos Noite", value=3)
    num_dia = st.number_input("Nº Médicos Dia (12h)", value=3)
    num_manha = st.number_input("Nº Médicos Manhã", value=3)
    
    st.divider()
    st.header("⚖️ Regras de Equidade")
    # NOVAS REGRAS DE CONTROLO
    max_noites_semana = st.number_input("Máx. Noites/Semana (Rolling 7 dias)", value=2, help="Impede que alguém faça 3 noites em 7 dias.")
    max_turnos_semana = st.number_input("Máx. Turnos Totais/Semana", value=4, help="Evita sobrecarga semanal.")
    usar_equipas = st.checkbox("🛡️ Proteger Equipas", value=True)
    regra_fds_unico = st.checkbox("🚫 Fim de Semana '1 Tiro'", value=True)

# Calcular dias
num_days = calendar.monthrange(ano, mes)[1]
datas = [date(ano, mes, day) for day in range(1, num_days + 1)]

# ==========================================
# 1. INPUT DE DADOS
# ==========================================
tab_equipa, tab_ausencias = st.tabs(["👥 Equipa", "✈️ Ausências"])

with tab_equipa:
    st.info("💡 O algoritmo agora vai tentar que todos tenham o mesmo nº de Noites e FDS.")
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
if col_act.button("🚀 GERAR ESCALA EQUILIBRADA", type="primary"):
    
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
    
    # Variáveis
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            for t in turnos:
                shifts[(m['index'], dia, t)] = model.NewBoolVar(f"s_{m['index']}_{dia}_{t}")

    # Variáveis 24h
    shifts_24h = {}
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            shifts_24h[(m['index'], dia)] = model.NewBoolVar(f"is_24h_{m['index']}_{dia}")
            model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] == 2).OnlyEnforceIf(shifts_24h[(m['index'], dia)])
            model.Add(shifts[(m['index'], dia, 'DIA')] + shifts[(m['index'], dia, 'NOITE')] < 2).OnlyEnforceIf(shifts_24h[(m['index'], dia)].Not())

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

        # Regra FDS '1 Tiro'
        if regra_fds_unico and data_obj.weekday() == 4: # Sexta
            s = dia; sab = dia + 1; dom = dia + 2
            if sab <= num_days and dom <= num_days:
                for m in medicos:
                    sexta_noite = shifts[(m['index'], s, 'NOITE')]
                    sabado_tot = sum(shifts[(m['index'], sab, t)] for t in turnos)
                    domingo_tot = sum(shifts[(m['index'], dom, t)] for t in turnos)
                    model.Add(sexta_noite + sabado_tot + domingo_tot <= 1)

    # --- NOVA LÓGICA DE EQUIDADE (JANELAS MÓVEIS) ---
    for m in medicos:
        # Descanso Pós-Noite
        for d_idx in range(len(datas) - 1):
            dia = d_idx + 1
            trabalhou_noite = shifts[(m['index'], dia, 'NOITE')]
            trabalhou_amanha = sum(shifts[(m['index'], dia+1, t)] for t in turnos)
            model.Add(trabalhou_noite + trabalhou_amanha <= 1)

        # 1. MÁXIMO NOITES POR SEMANA (Rolling Window 7 dias)
        # Impede o "cluster" de noites (ex: 3 noites em 5 dias)
        for d_idx in range(len(datas) - 6):
            # Soma as noites nos próximos 7 dias
            noites_janela = sum(shifts[(m['index'], d_idx + k + 1, 'NOITE')] for k in range(7))
            model.Add(noites_janela <= max_noites_semana)

        # 2. MÁXIMO TURNOS TOTAIS POR SEMANA (Evitar exaustão)
        for d_idx in range(len(datas) - 6):
            turnos_janela = sum(shifts[(m['index'], d_idx + k + 1, t)] for k in range(7) for t in turnos)
            model.Add(turnos_janela <= max_turnos_semana)

    # --- PREPARAÇÃO PARA OBJETIVO (CONTADORES) ---
    # Vamos contar Noites e Fins de Semana para nivelar
    total_noites_medico = []
    total_fds_medico = []
    
    # Identificar índices dos dias de FDS
    indices_fds = [d_idx for d_idx, d in enumerate(datas) if d.weekday() >= 5]
    
    for m in medicos:
        # Contar Noites
        n_noites = sum(shifts[(m['index'], d+1, 'NOITE')] for d in range(len(datas)))
        n_var = model.NewIntVar(0, 31, f"n_noites_{m['index']}")
        model.Add(n_var == n_noites)
        total_noites_medico.append(n_var)
        
        # Contar FDS Trabalhados (Se trabalha Sáb ou Dom, conta 1)
        fds_vars = []
        # Agrupar por Fim de Semana (Sábado + Domingo)
        # Simplificação: Iterar pelos Sábados
        for d_idx in range(len(datas)):
            if datas[d_idx].weekday() == 5: # Sábado
                sab_idx = d_idx
                dom_idx = d_idx + 1
                if dom_idx < len(datas):
                    # Trabalhou Sáb ou Dom?
                    trabalhou_sab = sum(shifts[(m['index'], sab_idx+1, t)] for t in turnos)
                    trabalhou_dom = sum(shifts[(m['index'], dom_idx+1, t)] for t in turnos)
                    # Criar booleana: 1 se trabalhou no FDS
                    touched_fds = model.NewBoolVar(f"fds_{m['index']}_{sab_idx}")
                    model.Add(trabalhou_sab + trabalhou_dom > 0).OnlyEnforceIf(touched_fds)
                    model.Add(trabalhou_sab + trabalhou_dom == 0).OnlyEnforceIf(touched_fds.Not())
                    fds_vars.append(touched_fds)
        
        if fds_vars:
            n_fds = sum(fds_vars)
            f_var = model.NewIntVar(0, 5, f"n_fds_{m['index']}")
            model.Add(f_var == n_fds)
            total_fds_medico.append(f_var)

    # --- OBJETIVO: NIVELAMENTO AGRESSIVO ---
    obj_terms = []

    # 1. Equidade de NOITES (Minimizar desvio da média)
    # Penalizar o quadrado da diferença (para punir outliers severamente) é difícil em CP-SAT linear.
    # Vamos minimizar a diferença entre Max e Min Noites.
    max_noites = model.NewIntVar(0, 31, 'max_noites')
    min_noites = model.NewIntVar(0, 31, 'min_noites')
    model.AddMaxEquality(max_noites, total_noites_medico)
    model.AddMinEquality(min_noites, total_noites_medico)
    obj_terms.append((max_noites - min_noites) * -500) # Peso muito alto

    # 2. Equidade de FINS DE SEMANA
    if total_fds_medico:
        max_fds = model.NewIntVar(0, 5, 'max_fds')
        min_fds = model.NewIntVar(0, 5, 'min_fds')
        model.AddMaxEquality(max_fds, total_fds_medico)
        model.AddMinEquality(min_fds, total_fds_medico)
        obj_terms.append((max_fds - min_fds) * -500)

    # 3. Equidade de HORAS TOTAIS
    # (Reutilizando lógica anterior para desempatar)
    total_horas = []
    for m in medicos:
        h = sum(shifts[(m['index'], d+1, 'MANHA')]*6 + 
                shifts[(m['index'], d+1, 'DIA')]*12 + 
                shifts[(m['index'], d+1, 'NOITE')]*12 for d in range(len(datas)))
        hv = model.NewIntVar(0, 300, f"h_{m['index']}")
        model.Add(hv == h)
        total_horas.append(hv)
    
    max_h = model.NewIntVar(0, 300, 'max_h')
    min_h = model.NewIntVar(0, 300, 'min_h')
    model.AddMaxEquality(max_h, total_horas)
    model.AddMinEquality(min_h, total_horas)
    obj_terms.append((max_h - min_h) * -100)

    # 4. Preferências (Menor peso que a equidade)
    for m in medicos:
        for d_idx, _ in enumerate(datas):
            dia = d_idx + 1
            if (m['nome'], dia) in soft_pedidos:
                trabalha = sum(shifts[(m['index'], dia, t)] for t in turnos)
                obj_terms.append(trabalha * -2000) # Pedido é sagrado
            
            if m['pref_24h']:
                obj_terms.append(shifts_24h[(m['index'], dia)] * 50)
            else:
                obj_terms.append(shifts_24h[(m['index'], dia)] * -50)

    model.Maximize(sum(obj_terms))

    # --- RESOLVER ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    # Dica para o solver focar em encontrar boas soluções rápido
    solver.parameters.linearization_level = 0 
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✅ Escala Nivelada com Sucesso!")
        
        dados_grelha = []
        stats = []
        pedidos_recusados = []
        fds_cols = [str(d_idx + 1) for d_idx, d in enumerate(datas) if d.weekday() >= 5]

        # Calcular Médias para mostrar no Dashboard
        # Extrair valores finais
        vals_noites = [solver.Value(v) for v in total_noites_medico]
        vals_fds = [solver.Value(v) for v in total_fds_medico] if total_fds_medico else []
        avg_noites = sum(vals_noites) / len(vals_noites) if vals_noites else 0
        avg_fds = sum(vals_fds) / len(vals_fds) if vals_fds else 0

        for idx, m in enumerate(medicos):
            row = {"Médico": m['nome'], "Eq": m['equipa']}
            n_24h = 0; n_noites_real = 0; n_fds_real = 0
            horas_totais = solver.Value(total_horas[idx])
            
            # Recontar FDS visualmente
            fds_count = 0
            for d_idx in range(len(datas)):
                if datas[d_idx].weekday() == 5: # Sabado
                    sab = d_idx + 1; dom = d_idx + 2
                    trab_fds = 0
                    if dom <= len(datas):
                        trab_fds = sum(solver.Value(shifts[(m['index'], sab, t)]) + solver.Value(shifts[(m['index'], dom, t)]) for t in turnos)
                    if trab_fds > 0: fds_count += 1
            
            for d_idx, data_obj in enumerate(datas):
                dia = d_idx + 1
                is_dia = solver.Value(shifts[(m['index'], dia, 'DIA')])
                is_noite = solver.Value(shifts[(m['index'], dia, 'NOITE')])
                is_manha = solver.Value(shifts[(m['index'], dia, 'MANHA')])
                
                label = ""
                if is_dia and is_noite: label = "DN"; n_24h += 1
                elif is_dia: label = "D"
                elif is_noite: label = "N"; n_noites_real += 1
                elif is_manha: label = "M"
                
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

            contrato_val = m.get('contrato') or 0
            horas_extra = horas_totais - (contrato_val * 4)
            
            dados_grelha.append(row)
            stats.append({
                "Médico": m['nome'], 
                "Noites": n_noites_real + n_24h,
                "FDS": fds_count,
                "Horas": horas_totais,
                "Delta Noites": (n_noites_real + n_24h) - avg_noites, # Desvio da média
                "Delta FDS": fds_count - avg_fds
            })

        st.subheader(f"Mapa Mensal - {calendar.month_name[mes]} {ano}")
        if pedidos_recusados: st.warning(f"⚠️ Pedidos Recusados: {', '.join(pedidos_recusados)}")
        
        df_grelha = pd.DataFrame(dados_grelha)
        
        def highlight_cells(val):
            style = ''
            if val == 'DN': style = 'background-color: #ff4d4d; color: white; font-weight: bold'
            elif val == 'N': style = 'background-color: #4da6ff; color: white'
            elif val == 'D': style = 'background-color: #85e085; color: black'
            elif val == 'M': style = 'background-color: #fff5cc; color: black'
            elif val == 'FER': style = 'background-color: #ffd700; color: black; font-weight: bold'
            elif val == 'CIT': style = 'background-color: #d8bfd8; color: black'
            elif val == 'CGS': style = 'background-color: #a9a9a9; color: white; text-decoration: line-through'
            elif val == 'PED': style = 'background-color: #ccffcc; color: black; border: 2px dashed green'
            return style

        styler = df_grelha.style.applymap(highlight_cells)
        styler.set_properties(subset=fds_cols, **{'background-color': '#e0e0e0', 'border-left': '2px solid #333', 'border-right': '2px solid #333'})
        st.dataframe(styler, use_container_width=True)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("⚖️ Indicadores de Desvio (Ideal = 0)")
            df_stats = pd.DataFrame(stats).set_index("Médico")
            
            # Colorir desvios
            def color_delta(val):
                if abs(val) < 1.0: return 'color: green; font-weight: bold' # Desvio mínimo
                if abs(val) < 2.0: return 'color: orange; font-weight: bold'
                return 'color: red; font-weight: bold' # Desvio grave

            st.dataframe(df_stats.style.applymap(color_delta, subset=['Delta Noites', 'Delta FDS']), use_container_width=True)
            
        with col2:
            st.info(f"**Médias da Equipa:**\n- Noites: {avg_noites:.1f}\n- Fim de Semana: {avg_fds:.1f}\n\nO objetivo é que o 'Delta' de todos esteja perto de 0.")
            st.download_button("📥 Baixar CSV", df_grelha.to_csv().encode('utf-8'), "escala_nivelada.csv")

    else:
        st.error("❌ Impossível gerar. Tente relaxar as regras de 'Máx. Noites/Semana' ou adicionar mais médicos.")
