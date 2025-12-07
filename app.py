import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model

# Configuração da Página
st.set_page_config(page_title="Gestão de Escalas Médicas", layout="wide")

st.title("🏥 Gerador Automático de Escalas (UCI & Urgência)")
st.markdown("Edite a lista de médicos abaixo e clique em **Gerar Escala**.")

# ==========================================
# 1. INTERFACE DE DADOS (Tabela Editável)
# ==========================================
# Dados Iniciais (Exemplo)
default_data = [
    {"nome": "Dr. Silva (Chefe)", "cargo": "ESPECIALISTA", "ativo": True},
    {"nome": "Dr. Costa", "cargo": "ESPECIALISTA", "ativo": True},
    {"nome": "Dra. Ana", "cargo": "ESPECIALISTA", "ativo": True},
    {"nome": "Dr. Pedro", "cargo": "INTERNO_SENIOR", "ativo": True},
    {"nome": "Dra. Sofia", "cargo": "INTERNO_SENIOR", "ativo": True},
    {"nome": "Dr. Rui", "cargo": "INTERNO_INICIAL", "ativo": True},
    {"nome": "Dra. Marta", "cargo": "INTERNO_INICIAL", "ativo": True},
    {"nome": "Dr. Tarefeiro A", "cargo": "TAREFEIRO", "ativo": True},
]

# Transformar em DataFrame para o Streamlit mostrar
df = pd.DataFrame(default_data)

# Mostrar Tabela Editável
col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Equipa Médica")
    # O widget data_editor permite adicionar/remover linhas no site!
    edited_df = st.data_editor(df, num_rows="dynamic")

with col2:
    st.info("ℹ️ **Regras Ativas:**\n\n- Mínimo 2 UCI + 1 SE por turno.\n- Interno Inicial não faz SE.\n- Descanso 24h pós-noite obrigatório.")
    dias_calcular = st.slider("Quantos dias calcular?", 1, 31, 7)
    botao_gerar = st.button("🚀 Gerar Escala Agora", type="primary")

# ==========================================
# 2. O MOTOR (Só corre se carregar no botão)
# ==========================================
if botao_gerar:
    # Preparar dados para o algoritmo
    medicos = []
    # Converter o que está na tabela para a lista do algoritmo
    for index, row in edited_df.iterrows():
        if row['ativo']:
            medicos.append({'id': index, 'nome': row['nome'], 'cargo': row['cargo']})
    
    if len(medicos) < 5:
        st.error("⚠️ Precisa de mais médicos ativos para cobrir a escala!")
    else:
        st.write("🔄 A calcular a melhor combinação matemática...")
        
        # --- INICIO DO ALGORITMO OR-TOOLS ---
        dias = range(dias_calcular)
        turnos = ['MANHA', 'DIA', 'NOITE'] 
        postos = ['UCI', 'SE'] 
        model = cp_model.CpModel()
        shifts = {}

        # Variáveis
        for m in medicos:
            for d in dias:
                for t in turnos:
                    for p in postos:
                        shifts[(m['id'], d, t, p)] = model.NewBoolVar(f"shift_{m['id']}_{d}_{t}_{p}")

        # Regras Hard
        for d in dias:
            model.Add(sum(shifts[(m['id'], d, 'DIA', 'UCI')] for m in medicos) >= 2)
            model.Add(sum(shifts[(m['id'], d, 'DIA', 'SE')] for m in medicos) >= 1)
            model.Add(sum(shifts[(m['id'], d, 'NOITE', 'UCI')] for m in medicos) >= 2)
            model.Add(sum(shifts[(m['id'], d, 'NOITE', 'SE')] for m in medicos) >= 1)

        for m in medicos:
            for d in dias:
                model.Add(sum(shifts[(m['id'], d, t, p)] for t in turnos for p in postos) <= 1)
            
            if m['cargo'] == 'INTERNO_INICIAL':
                for d in dias:
                    for t in turnos:
                        model.Add(shifts[(m['id'], d, t, 'SE')] == 0)
            
            # Descanso Pós-Noite
            for d in range(dias_calcular - 1):
                trabalhou_noite = sum(shifts[(m['id'], d, 'NOITE', p)] for p in postos)
                trabalhou_amanha = sum(shifts[(m['id'], d+1, t, p)] for t in turnos for p in postos)
                model.Add(trabalhou_noite + trabalhou_amanha <= 1)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(model)

        # --- FIM DO ALGORITMO / APRESENTAÇÃO ---
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            st.success("✅ Escala Gerada com Sucesso!")
            
            # Criar Tabs para cada dia
            tabs = st.tabs([f"Dia {d+1}" for d in dias])
            
            for d in dias:
                with tabs[d]:
                    col_escala, col_ane = st.columns(2)
                    
                    staff_ocupado = []
                    escala_dia = []
                    
                    # Recolher dados
                    for m in medicos:
                        for t in turnos:
                            for p in postos:
                                if solver.Value(shifts[(m['id'], d, t, p)]) == 1:
                                    escala_dia.append({"Médico": m['nome'], "Cargo": m['cargo'], "Turno": t, "Posto": p})
                                    staff_ocupado.append(m['id'])
                    
                    with col_escala:
                        st.subheader("📋 Escala Clínica")
                        st.table(pd.DataFrame(escala_dia))
                    
                    with col_ane:
                        st.subheader("🔵 Disponíveis (ANE/Reforço)")
                        ane_list = []
                        for m in medicos:
                            if m['id'] not in staff_ocupado:
                                # Check descanso simples
                                pode = True
                                if d > 0:
                                    ontem_noite = sum(solver.Value(shifts[(m['id'], d-1, 'NOITE', p)]) for p in postos)
                                    if ontem_noite > 0: pode = False
                                
                                if pode:
                                    ane_list.append(f"{m['nome']} ({m['cargo']})")
                        
                        if ane_list:
                            for p in ane_list:
                                st.write(f"- {p}")
                        else:
                            st.warning("Sem médicos extra disponíveis.")

        else:
            st.error("❌ Impossível gerar escala. Tente adicionar mais médicos na tabela acima.")
