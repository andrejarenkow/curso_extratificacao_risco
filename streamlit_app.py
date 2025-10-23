# streamlit_app_v3.py
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import seaborn as sns

st.set_page_config(page_title="Dashboard Dengue & Vigiágua", layout="wide")

sns.set_style("white")
sns.despine()

# ---------- Funções utilitárias e cache ----------

@st.cache_data(ttl=3600)
def carregar_codigos_ibge():
    url = 'https://www.gov.br/receitafederal/dados/municipios.csv'
    df = pd.read_csv(url, encoding='latin1', sep=';')
    rs = df[df['UF'] == 'RS']
    return rs

@st.cache_data(ttl=1800)
def get_last_counting_public(municipality):
    dados = pd.DataFrame()
    page = 1
    while True:
        url = f"https://contaovos.com/pt-br/api/lastcountingpublic?municipality={municipality}&page={page}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
        except Exception:
            break
        if not data:
            break
        df = pd.DataFrame(data)
        dados = pd.concat([dados, df], ignore_index=True)
        page += 1
        if page > 200:
            break
    return dados

def get_ido(df):
    return float(df[df['eggs'] > 0]['eggs'].mean()) if not df.empty else None

def get_ipo(df):
    return float(((df['eggs'] > 0).sum() / len(df)).round(4)) if (not df.empty and len(df) > 0) else None

def get_imo(df):
    return float(df['eggs'].mean()) if (not df.empty and 'eggs' in df.columns) else None

@st.cache_data(ttl=1800)
def buscar_dados_dengue(nome_municipio, SEi, SEf, ano_inicial, ano_final, cod_ibge7_rs_dict):
    url = "https://info.dengue.mat.br/api/alertcity"
    geocode = cod_ibge7_rs_dict.get(nome_municipio)
    if geocode is None:
        return pd.DataFrame()
    disease = "dengue"
    format = "csv"
    params = (
        "&disease=" + f"{disease}"
        + "&geocode=" + f"{geocode}"
        + "&format=" + f"{format}"
        + "&ew_start=" + f"{SEi}"
        + "&ew_end=" + f"{SEf}"
        + "&ey_start=" + f"{ano_inicial}"
        + "&ey_end=" + f"{ano_final}"
    )
    url_resp = "?".join([url, params])
    try:
        dados = pd.read_csv(url_resp)
    except Exception:
        return pd.DataFrame()
    return dados

@st.cache_data(ttl=1800)
def buscar_parametros_sisagua(municipio: str, ano: int, cod_ibge7_rs_dict=None):
    if cod_ibge7_rs_dict is None or municipio not in cod_ibge7_rs_dict:
        return pd.DataFrame()
    lista_parametros = [
        'Cloro residual livre (mg/L)',
        'Fluoreto (mg/L)',
        'Escherichia coli',
        'Turbidez (uT)',
        'Coliformes totais',
        'Cloro residual combinado (mg/L)'
    ]

    url = "https://apidadosabertos.saude.gov.br/sisagua/vigilancia-parametros-basicos"
    headers = {"accept": "application/json"}
    codigo_ibge = str(cod_ibge7_rs_dict[municipio])[:6]

    limit = 1000
    dados_totais = []

    for parametro_da_vez in lista_parametros:
        offset = 0
        dados = []
        amostras_vistas = set()
        while True:
            params = {
                "codigo_ibge": codigo_ibge,
                "ano": str(ano),
                "limit": limit,
                "offset": offset,
                "parametro": parametro_da_vez
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=20)
                if r.status_code != 200:
                    break
                data = r.json()
            except Exception:
                break
            df_temp = pd.DataFrame(data)
            if df_temp.empty or "parametros" not in df_temp.columns:
                break
            df_norm = pd.json_normalize(df_temp["parametros"])
            if "numero_da_amostra" in df_norm.columns:
                novos = df_norm[~df_norm["numero_da_amostra"].isin(amostras_vistas)]
                if novos.empty:
                    break
                amostras_vistas.update(df_norm["numero_da_amostra"])
            dados.append(df_norm)
            offset += 1
            if offset > 300:
                break
        if dados:
            df_param = pd.concat(dados, ignore_index=True)
            df_param["parametro_consultado"] = parametro_da_vez
            dados_totais.append(df_param)
    return pd.concat(dados_totais, ignore_index=True) if dados_totais else pd.DataFrame()

# ---------- Interface ----------

st.title("Dashboard Dengue & Vigiágua — RS")
st.markdown("Dashboard integrado com dados de **ContaOvos**, **InfoDengue** e **SisÁgua (Vigiágua)**.")

codigos = carregar_codigos_ibge()
municipios = sorted(codigos['MUNICÍPIO - IBGE'].unique().tolist())
cod_ibge7_rs_dict = dict(zip(codigos['MUNICÍPIO - IBGE'], codigos['CÓDIGO DO MUNICÍPIO - IBGE']))

with st.sidebar:
    st.header("Parâmetros")
    municipio = st.selectbox("Município (RS)", municipios, index=municipios.index("Sapucaia do Sul") if "Sapucaia do Sul" in municipios else 0)
    ano = st.number_input("Ano", min_value=2000, max_value=2100, value=2025, step=1)
    atualizar = st.button("Atualizar / Recarregar")

if not atualizar:
    st.info("👈 Selecione o município e o ano e clique em **Atualizar / Recarregar** para carregar os dados.")
else:
    with st.spinner("Carregando dados das APIs..."):
        dados_municipio = get_last_counting_public(municipio)
        dados_infodengue = buscar_dados_dengue(municipio, 1, 52, ano, ano, cod_ibge7_rs_dict)
        dados_parametros = buscar_parametros_sisagua(municipio, ano, cod_ibge7_rs_dict)
    st.success("✅ Dados carregados com sucesso!")

    # ---------- Abas ----------
    tab1, tab2, tab3 = st.tabs(["🦟 Dengue", "💧 Vigiágua", "📊 Resumo"])

    # --- TAB 1: DENGUE ---
    with tab1:
        st.subheader(f"Dengue — {municipio} ({ano})")

        if dados_municipio.empty and dados_infodengue.empty:
            st.info("Sem dados disponíveis para este município/ano.")
        else:
            # Calcular IPO
            if not dados_municipio.empty and 'week' in dados_municipio.columns and 'year' in dados_municipio.columns:
                dados_ipo = dados_municipio.groupby(['week','year']).apply(get_ipo).reset_index()
                dados_ipo.columns = ['Semana Epidemiológica','Ano','IPO']
                dados_ipo = dados_ipo[dados_ipo['Ano'] == int(ano)]
                dados_ipo['IPO'] = dados_ipo['IPO'] * 100
            else:
                dados_ipo = pd.DataFrame(columns=['Semana Epidemiológica','IPO'])

            # Preparar dados InfoDengue
            if not dados_infodengue.empty:
                dados_infodengue['Semana Epidemiológica'] = dados_infodengue['SE'].astype(str).str[-2:].astype(int)
            else:
                dados_infodengue = pd.DataFrame(columns=['Semana Epidemiológica','casos_est'])

            # Criar gráfico combinado
            fig = go.Figure()

            if not dados_infodengue.empty:
                fig.add_trace(go.Bar(
                    x=dados_infodengue['Semana Epidemiológica'],
                    y=dados_infodengue['casos_est'],
                    name='Casos Estimados',
                    marker_color='indianred',
                    opacity=0.6,
                    yaxis='y1'
                ))

            if not dados_ipo.empty:
                fig.add_trace(go.Scatter(
                    x=dados_ipo['Semana Epidemiológica'],
                    y=dados_ipo['IPO'],
                    name='IPO (%)',
                    mode='lines+markers',
                    line=dict(color='darkblue', width=3),
                    yaxis='y2'
                ))

            fig.update_layout(
                title=f"Casos Estimados (InfoDengue) e IPO (ContaOvos) — {municipio} ({ano})",
                xaxis_title="Semana Epidemiológica",
                yaxis=dict(title="Casos Estimados", showgrid=False),
                yaxis2=dict(title="IPO (%)", overlaying='y', side='right', showgrid=False),
                legend=dict(x=0.02, y=0.98),
                template='plotly_white',
                height=500
            )

            st.plotly_chart(fig, use_container_width=True)


    # --- TAB 2: VIGIÁGUA ---
    with tab2:
        st.subheader(f"Vigiágua — {municipio} ({ano})")
    
        if dados_parametros.empty:
            st.info("Sem registros Vigiágua para este município/ano.")
        else:
            # Normalizar resultados
            dados_parametros['resultado'] = dados_parametros['resultado'].astype(str).str.replace(',', '.')
            dados_parametros['resultado_num'] = pd.to_numeric(dados_parametros['resultado'], errors='coerce')
    
            # Classificação simples conforme tipo de parâmetro
            def classificar(row):
                p = row.get('parametro_consultado', '')
                r = row.get('resultado_num', None)
                v = row.get('resultado', '').upper()
                if pd.isna(r) and not v:
                    return 'Sem resultado'
                if 'Turbidez' in p:
                    return 'Insatisfatória' if (pd.notna(r) and r > 5) else 'Satisfatória'
                elif 'Escherichia' in p:
                    return 'Insatisfatória' if v == 'PRESENTE' else 'Satisfatória'
                elif 'Fluoreto' in p:
                    if 0.6 <= r <= 0.9 and row['tipo_da_forma_de_abastecimento'] == 'SAA':
                        return 'Satisfatória'

                    elif 0 <= r['resultado'] <= 1.5 and r['tipo_da_forma_de_abastecimento'] in ['SAC', 'SAI', 'CARRO-PIPA']:
                        return 'Satisfatória'
                    
                    else:
                        return 'Insatisfatória'
                elif 'Cloro residual livre' in p:
                    return 'Insatisfatória' if (r < 0.2 or r > 5) else 'Satisfatória'
                elif 'Cloro residual combinado' in p:
                    return 'Insatisfatória' if (pd.notna(r) and r < 2) else 'Satisfatória'
                else:
                    return 'Satisfatória'
    
            dados_parametros['Classificação'] = dados_parametros.apply(classificar, axis=1)
    
            # Agrupar contagens por parâmetro
            resumo = (
                dados_parametros.groupby(['parametro_consultado', 'Classificação'])
                .size()
                .reset_index(name='Contagem')
            )
    
            st.markdown("### Classificação da qualidade da água")
            
    
            # Criar gráficos de pizza por parâmetro
            parametros = resumo['parametro_consultado'].unique()
            cols = st.columns(len(parametros))
    
            for i, param in enumerate(parametros):
                sub = resumo[resumo['parametro_consultado'] == param]
                fig = px.pie(
                    sub,
                    names='Classificação',
                    values='Contagem',
                    title=param,
                    color='Classificação',
                    color_discrete_map={
                        'Satisfatória': '#2CA02C',
                        'Insatisfatória': 'indianred',
                        'Sem resultado': 'gray'
                    }
                )
                cols[i].plotly_chart(fig, use_container_width=True)

            st.dataframe(resumo)


    # --- TAB 3: RESUMO ---
    with tab3:
        st.subheader("Resumo geral")
        st.metric("Total registros ContaOvos", len(dados_municipio))
        st.metric("Total InfoDengue", len(dados_infodengue))
        st.metric("Total Vigiágua", len(dados_parametros))
        st.markdown("### Exportar dados")
        if not dados_infodengue.empty:
            st.download_button("⬇️ Baixar InfoDengue CSV", dados_infodengue.to_csv(index=False), f"infodengue_{municipio}_{ano}.csv")
        if not dados_parametros.empty:
            st.download_button("⬇️ Baixar Vigiágua CSV", dados_parametros.to_csv(index=False), f"vigiagua_{municipio}_{ano}.csv")

st.markdown("---")
st.caption("© Dashboard desenvolvido com dados públicos — adaptável para uso em municípios do RS.")
