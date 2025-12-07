import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import date, timedelta
import calendar

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Gestão de Escalas Médicas Pro", layout="wide")

st.title("🏥 Gestor de Escalas Médicas (UCI & Urgência)")

# --- BARRA LATERAL (Configurações) ---
with st.sidebar:
    st.header("📅 Configuração do Mês")
    ano = st.number_input("Ano", min_value=2024, max_value=2030, value=2025)
    mes = st.selectbox("Mês", range(1, 13), index=0)
    
    st.divider()
    st.header("⚙️ Regras de Negócio")
    permitir_24h = st.checkbox("Permitir turnos 24h (Dia + Noite seguidos)?", value=False)
    min_uci = st.number_input("Mínimo UCI (Dia/Noite)", value=2)
    min_se = st.number_input("Mínimo SE (Dia/Noite)", value=1)

# Calcular dias do mês selecionado
num_days = calendar.monthrange(ano, mes)[1]
datas = [date(ano, mes, day) for day in range(1, num_days + 1)]

# ==========================================
# 1. INPUT DE DADOS (Médicos e Ausências)
# ==========================================
tab_medicos, tab_ausencias = st.tabs(["👥 Equipa Médica", "✈️ Ausências & Férias"])

with tab_medicos:
    # Adicionei coluna 'Equipa' para futuro uso de agrupamento
    default_medicos = [
        {"nome": "Dr. Silva (Chefe)", "cargo": "ESPECIALISTA", "equipa": "A", "horas_contrato": 36, "ativo": True},
        {"nome": "Dr. Costa", "cargo": "ESPECIALISTA", "equipa": "B", "horas_contrato": 36, "ativo": True},
        {"nome": "Dra. Ana", "cargo": "ESPECIALISTA", "equipa": "A", "horas_contrato": 36, "ativo": True},
        {"nome": "Dr. Pedro", "cargo": "INTERNO_SENIOR", "equipa": "B", "horas_contrato": 36, "ativo": True},
        {"nome": "Dra. Sofia", "cargo": "INTERNO_SENIOR", "equipa": "C", "horas_contrato": 36, "ativo": True},
        {"nome": "Dr. Rui", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "horas_contrato": 40, "ativo": True},
        {"nome": "Dra. Marta", "cargo": "INTERNO_INICIAL", "equipa": "Rot", "horas_contrato": 40, "ativo": True},
        {"nome": "Dr. Tarefeiro A", "cargo": "TAREFEIRO", "equipa": "Ext", "horas_contrato": 0, "ativo": True},
    ]
    df_medicos = st.data_editor(pd.DataFrame(default_medicos), num_rows="dynamic", use_container_width=True)

with tab_ausencias:
    st.info("Introduza os dias em que o médico NÃO pode trabalhar.")
    default_ausencias = [{"nome": "Dr. Silva (Chefe)", "dia": 1}, {"nome": "Dr. Silva (Chefe)", "dia": 2}]
    df_ausencias = st.data_editor(pd.DataFrame(default_ausencias), num_rows="dynamic", use_container_width=True)

# ==========================================
# 2. BOTÃO DE GERAR ESCALA
# ==========================================
st.divider()
col_btn, col_info = st.columns([1, 4])
gerar = col_btn.button("🚀 GERAR ESCALA", type="primary", use_container_width=True)

if gerar:
    # Preparar Dados
    medicos_ativos = df_medicos[df_medicos["ativo"] == True].reset_index()
    lista_medicos = medicos_ativos.to_dict('records')
    
    # Mapear Ausências (Nome -> Lista de Dias)
    ausencias_dict = {}
    for _, row in df_ausencias.iterrows():
        if row['nome'] not in ausencias_dict: ausencias_dict[row['nome']] = []
        ausencias_dict[row['nome']].append(row['dia'])

    # --- MOTOR OR-TOOLS ---
    model = cp_model.CpModel()
    shifts = {}
    turnos = ['MANHA', 'DIA', 'NOITE'] # Manhã é reforço, Dia/Noite são 12h
    postos = ['UCI', 'SE']

    # Criar Variáveis
    for m in lista_medicos:
        for d_idx, data_obj in enumerate(datas):
            dia_num = d_idx + 1
            for t in turnos:
                for p in postos:
                    shifts[(m['index'], dia_num, t, p)] = model.NewBoolVar(f"shift_{m['index']}_{dia_num}_{t}_{p}")

    # --- REGRAS (HARD CONSTRAINTS) ---
    for d_idx, data_obj in enumerate(datas):
        dia_num = d_idx + 1
        is_weekend = data_obj.weekday() >= 5 # 5=Sábado, 6=Domingo

        # 1. Cobertura Mínima
        model.Add(sum(shifts[(m['index'], dia_num, 'DIA', 'UCI')] for m in lista_medicos) >= min_uci)
        model.Add(sum(shifts[(m['index'], dia_num, 'NOITE', 'UCI')] for m in lista_medicos) >= min_uci)
        
        model.Add(sum(shifts[(m['index'], dia_num, 'DIA', 'SE')] for m in lista_medicos) >= min_se)
        model.Add(sum(shifts[(m['index'], dia_num, 'NOITE', 'SE')] for m in lista_medicos) >= min_se)

        # 2. Competência (Interno Inicial não faz SE)
        for m in lista_medicos:
            if m['cargo'] == 'INTERNO_INICIAL':
                for t in turnos:
                    model.Add(shifts[(m['index'], dia_num, t, 'SE')] == 0)
            
            # 3. Ausências Individuais
            if m['nome'] in ausencias_dict and dia_num in ausencias_dict[m['nome']]:
                 for t in turnos:
                    for p in postos:
                        model.Add(shifts[(m['index'], dia_num, t, p)] == 0)

            # 4. Um médico não pode estar em dois sítios ao mesmo tempo
            model.Add(sum(shifts[(m['index'], dia_num, t, p)] for t in turnos for p in postos) <= 1)

    # 5. Regras de Descanso e Sequência
    for m in lista_medicos:
        for d_idx in range(len(datas) - 1):
            dia_atual = d_idx + 1
            dia_seguinte = dia_atual + 1
            
            # Se permitir 24h: Pode fazer DIA + NOITE no mesmo dia.
            # Mas se fizer NOITE, folga no dia seguinte.
            
            trabalhou_noite = sum(shifts[(m['index'], dia_atual, 'NOITE', p)] for p in postos)
            trabalhou_dia = sum(shifts[(m['index'], dia_atual, 'DIA', p)] for p in postos)
            trabalhou_amanha = sum(shifts[(m['index'], dia_seguinte, t, p)] for t in turnos for p in postos)

            # Regra de Descanso Pós-Noite (UNIVERSAL)
            model.Add(trabalhou_noite + trabalhou_amanha <= 1)

            if not permitir_24h:
                # Se não permite 24h, Dia e Noite no mesmo dia são mutuamente exclusivos
                model.Add(trabalhou_dia + trabalhou_noite <= 1)

    # --- RESOLUÇÃO ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success(f"✅ Escala Gerada! (Status: {solver.StatusName(status)})")

        # ==========================================
        # 3. PÓS-PROCESSAMENTO E VISUALIZAÇÃO
        # ==========================================
        
        # Estruturas para guardar dados
        schedule_data = [] # Para a Matriz Visual
        stats_data = {m['nome']: {'Horas': 0, 'Noites': 0, 'Fins de Semana': 0, 'Contrato': m['horas_contrato']} for m in lista_medicos}

        for d_idx, data_obj in enumerate(datas):
            dia_num = d_idx + 1
            dia_str = data_obj.strftime("%d/%m")
            is_weekend = data_obj.weekday() >= 5
            
            for m in lista_medicos:
                texto_celula = ""
                for t in turnos:
                    for p in postos:
                        if solver.Value(shifts[(m['index'], dia_num, t, p)]) == 1:
                            # Texto para a matriz (Ex: "NOITE (UCI)")
                            texto_celula = f"{t[:1]}-{p}" # Ex: N-UCI, D-SE
                            
                            # Atualizar Estatísticas
                            horas = 12 if t in ['DIA', 'NOITE'] else 6
                            stats_data[m['nome']]['Horas'] += horas
                            
                            if t == 'NOITE':
                                stats_data[m['nome']]['Noites'] += 1
                            
                            if is_weekend:
                                stats_data[m['nome']]['Fins de Semana'] += 1
                
                schedule_data.append({
                    "Médico": m['nome'],
                    "Dia": dia_str,
                    "Turno": texto_celula
                })

        # --- A. TABELA MATRIZ (GANTT) ---
        df_schedule = pd.DataFrame(schedule_data)
        # Pivot para criar a grelha (Linhas=Médicos, Colunas=Dias)
        df_matrix = df_schedule.pivot(index="Médico", columns="Dia", values="Turno").fillna("")
        
        st.subheader("🗓️ Mapa da Escala")
        st.dataframe(df_matrix, use_container_width=True)

        # --- B. DASHBOARD DE EQUIDADE ---
        st.subheader("⚖️ Indicadores de Equidade")
        df_stats = pd.DataFrame.from_dict(stats_data, orient='index')
        df_stats['Saldo Horas'] = df_stats['Horas'] - (df_stats['Contrato'] * 4) # Estima 4 semanas
        
        # Colorir Saldo Negativo/Positivo
        def color_saldo(val):
            color = 'red' if val < 0 else 'green'
            return f'color: {color}'

        st.dataframe(df_stats.style.applymap(color_saldo, subset=['Saldo Horas']), use_container_width=True)

        # --- C. EXPORTAR ---
        col_download, _ = st.columns([1, 4])
        csv = df_matrix.to_csv().encode('utf-8')
        col_download.download_button(
            label="📥 Baixar Escala (CSV)",
            data=csv,
            file_name=f'escala_{mes}_{ano}.csv',
            mime='text/csv',
        )

    else:
        st.error("❌ Não foi possível gerar a escala. Verifique se tem médicos suficientes para cobrir os mínimos ou se as ausências bloqueiam dias críticos.")
