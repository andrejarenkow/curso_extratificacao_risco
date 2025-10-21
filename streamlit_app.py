# Criar arquivo streamlit_app.py com o dashboard solicitado.

import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from io import StringIO

st.set_page_config(page_title="Dashboard Dengue & Vigiágua", layout="wide")

sns.set_style("white")
sns.despine()

# ---------- Helpers & Cached API calls ----------

@st.cache_data(ttl=60*60)
def carregar_codigos_ibge():
    url = 'https://www.gov.br/receitafederal/dados/municipios.csv'
    df = pd.read_csv(url, encoding='latin1', sep=';')
    rs = df[df['UF']=='RS']
    return rs

@st.cache_data(ttl=30*60)
def get_last_counting_public(municipality):
    dados = pd.DataFrame()
    page = 1
    while True:
        url = f"https://contaovos.com/pt-br/api/lastcountingpublic?municipality={municipality}&page={page}"
        try:
            response = requests.get(url, timeout=20)
            data = response.json()
        except Exception:
            break
        if not data:
            break
        df = pd.DataFrame(data)
        dados = pd.concat([dados, df], ignore_index=True)
        page += 1
        # safety: avoid infinite loop
        if page > 200:
            break
    return dados

def get_ido(df):
    return float(df[df['eggs']>0]['eggs'].mean()) if not df.empty else None

def get_ipo(df):
    return float(((df['eggs']>0).sum()/len(df)).round(4)) if (not df.empty and len(df)>0) else None

def get_imo(df):
    return float(df['eggs'].mean()) if (not df.empty and 'eggs' in df.columns) else None

@st.cache_data(ttl=30*60)
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

@st.cache_data(ttl=30*60)
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
            else:
                novos = df_norm

            dados.append(df_norm)
            offset += 1

            # safety
            if offset > 500:
                break

        if dados:
            df_param = pd.concat(dados, ignore_index=True)
            df_param["parametro_consultado"] = parametro_da_vez
            dados_totais.append(df_param)

    return pd.concat(dados_totais, ignore_index=True) if dados_totais else pd.DataFrame()

# ---------- Layout / Inputs ----------

st.title("Dashboard Dengue & Vigiágua — RS")
st.markdown("Dashboard integrado: ContaOvos, InfoDengue e API SisÁgua (Vigiágua).")

codigos = carregar_codigos_ibge()
municipios = sorted(codigos['MUNICÍPIO - IBGE'].unique().tolist())
cod_ibge7_rs_dict = dict(zip(codigos['MUNICÍPIO - IBGE'], codigos['CÓDIGO DO MUNICÍPIO - IBGE']))

with st.sidebar:
    st.header("Parâmetros")
    municipio = st.selectbox("Município (RS)", municipios, index=municipios.index("Sapucaia do Sul") if "Sapucaia do Sul" in municipios else 0)
    ano = st.number_input("Ano", min_value=2000, max_value=2100, value=2025, step=1)
    atualizar = st.button("Atualizar / Recarregar")

# ---------- Tabs ----------

tab1, tab2, tab3, tab4 = st.tabs(["Dengue (ContaOvos + InfoDengue)", "Vigiágua (SisÁgua)", "Resumo", "Dados Brutos"])

# --- Tab 1: Dengue ---
with tab1:
    st.subheader(f"Dengue — {municipio} — {ano}")
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        st.markdown("**Indicadores ContaOvos**")
        dados_municipio = get_last_counting_public(municipio)
        ido = get_ido(dados_municipio) if not dados_municipio.empty else None
        ipo = get_ipo(dados_municipio) if not dados_municipio.empty else None
        imo = get_imo(dados_municipio) if not dados_municipio.empty else None

        st.metric("IDO (média ovos>0)", f"{ido:.2f}" if ido is not None else "N/A")
        st.metric("IPO (positividade %)", f"{ipo*100:.2f}%" if ipo is not None else "N/A")
        st.metric("IMO (média ovos)", f"{imo:.2f}" if imo is not None else "N/A")

    with col2:
        st.markdown("**Casos estimados (InfoDengue)**")
        dados_infodengue = buscar_dados_dengue(municipio, 1, 52, ano, ano, cod_ibge7_rs_dict)
        if not dados_infodengue.empty:
            # derive week column
            dados_infodengue['Semana Epidemiológica'] = dados_infodengue['SE'].astype(str).str[-2:].astype(int)
            fig = px.bar(dados_infodengue, x='Semana Epidemiológica', y='casos_est', labels={'casos_est':'Casos Estimados'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados InfoDengue para o município/ano selecionado.")

    with col3:
        st.markdown("**IPO por Semana (ContaOvos)**")
        if not dados_municipio.empty:
            # prepare IPO by week/year
            df = dados_municipio.copy()
            if 'week' in df.columns and 'year' in df.columns:
                df_ipo = df.groupby(['week','year']).apply(get_ipo).reset_index()
                df_ipo.columns = ['Semana Epidemiológica','Ano','IPO']
                df_ipo['IPO'] = df_ipo['IPO']*100
                df_ipo = df_ipo[df_ipo['Ano']==int(ano)]
                if not df_ipo.empty:
                    fig2 = px.line(df_ipo, x='Semana Epidemiológica', y='IPO', markers=True)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("Sem IPO para o ano selecionado.")
            else:
                st.info("Dados ContaOvos não possuem colunas 'week' e 'year' para plotar IPO.")
        else:
            st.info("Sem dados ContaOvos para o município selecionado.")

# --- Tab 2: Vigiágua ---
with tab2:
    st.subheader(f"Vigiágua — {municipio} — {ano}")
    dados_parametros = buscar_parametros_sisagua(municipio, ano, cod_ibge7_rs_dict)
    if dados_parametros.empty:
        st.info("Sem registros Vigiágua para este município/ano.")
    else:
        # Tratamentos comuns
        # Padroniza nome do parametro consultado
        dados_parametros = dados_parametros.reset_index(drop=True)
        # converte resultado quando for string numérica com vírgula
        if 'resultado' in dados_parametros.columns:
            try:
                dados_parametros['resultado'] = dados_parametros['resultado'].astype(str).str.replace(',', '.')
                dados_parametros['resultado_num'] = pd.to_numeric(dados_parametros['resultado'], errors='coerce')
            except Exception:
                dados_parametros['resultado_num'] = pd.to_numeric(dados_parametros['resultado'], errors='coerce')

        # Classificações exemplares
        def clas_fluoreto(row):
            if pd.isna(row['resultado_num']):
                return "Sem resultado"
            if 0.6 <= row['resultado_num'] <= 0.9 and row.get('tipo_da_forma_de_abastecimento','') == 'SAA':
                return 'Satisfatória'
            elif 0 <= row['resultado_num'] <= 1.5 and row.get('tipo_da_forma_de_abastecimento','') in ['SAC','SAI','CARRO-PIPA']:
                return 'Satisfatória'
            else:
                return 'Insatisfatória'

        # aplica por parametro
        if 'parametro_consultado' in dados_parametros.columns:
            # turbidez
            turb = dados_parametros[dados_parametros['parametro_consultado']=='Turbidez (uT)'].copy()
            if 'resultado' in turb.columns:
                turb['resultado'] = turb['resultado'].astype(str).str.replace(',', '.')
                turb['resultado_num'] = pd.to_numeric(turb['resultado'], errors='coerce')
                turb['Classificação'] = turb['resultado_num'].apply(lambda x: 'Insatisfatória' if x>5 else 'Satisfatória' if pd.notna(x) else 'Sem resultado')
            # e coli
            ecoli = dados_parametros[dados_parametros['parametro_consultado']=='Escherichia coli'].copy()
            if 'resultado' in ecoli.columns:
                ecoli['Classificação'] = ecoli['resultado'].apply(lambda x: 'Insatisfatória' if str(x).upper()=='PRESENTE' else 'Satisfatória')
            # fluoreto
            flu = dados_parametros[dados_parametros['parametro_consultado']=='Fluoreto (mg/L)'].copy()
            if not flu.empty:
                flu['resultado'] = flu['resultado'].astype(str).str.replace(',', '.')
                flu['resultado_num'] = pd.to_numeric(flu['resultado'], errors='coerce')
                flu['Classificação'] = flu.apply(clas_fluoreto, axis=1)
            # cloro livre
            cll = dados_parametros[dados_parametros['parametro_consultado']=='Cloro residual livre (mg/L)'].copy()
            if not cll.empty:
                cll['resultado'] = cll['resultado'].astype(str).str.replace(',', '.')
                cll['resultado_num'] = pd.to_numeric(cll['resultado'], errors='coerce')
                cll['Classificação'] = cll['resultado_num'].apply(lambda x: 'Insatisfatória' if (pd.notna(x) and (x>5 or x<0.2)) else ('Satisfatória' if pd.notna(x) else 'Sem resultado'))
            # cloro combinado
            clc = dados_parametros[dados_parametros['parametro_consultado']=='Cloro residual combinado (mg/L)'].copy()
            if not clc.empty:
                clc['resultado'] = clc['resultado'].astype(str).str.replace(',', '.')
                clc['resultado_num'] = pd.to_numeric(clc['resultado'], errors='coerce')
                clc['Classificação'] = clc['resultado_num'].apply(lambda x: 'Insatisfatória' if (pd.notna(x) and x<2) else ('Satisfatória' if pd.notna(x) else 'Sem resultado'))

            # concat pra visual
            frames = []
            for d in [cll, clc, flu, ecoli, turb]:
                if isinstance(d, pd.DataFrame) and not d.empty:
                    frames.append(d[['parametro_consultado','Classificação']].copy())
            if frames:
                resumo = pd.concat(frames, ignore_index=True)
                resumo_counts = resumo.groupby(['parametro_consultado','Classificação']).size().reset_index(name='count')
                # Mostrar tabela e graficos
                st.markdown("### Contagem por Classificação")
                st.dataframe(resumo_counts)
                # Pie charts por parâmetro usando plotly
                params = resumo_counts['parametro_consultado'].unique()
                cols = st.columns(len(params))
                for i,param in enumerate(params):
                    sub = resumo_counts[resumo_counts['parametro_consultado']==param]
                    fig = px.pie(sub, names='Classificação', values='count', title=param)
                    cols[i].plotly_chart(fig, use_container_width=True)
            else:
                st.info("Não foi possível gerar resumo de classificações para os parâmetros encontrados.")
        else:
            st.info("Estrutura inesperada dos dados Vigiágua (coluna 'parametro_consultado' não encontrada).")

# --- Tab 3: Resumo ---
with tab3:
    st.subheader("Resumo agregado")
    # Indicadores rápidos
    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Dengue (ContaOvos)**")
        if 'ido' in locals() and ido is not None:
            st.metric("IDO", f"{ido:.2f}")
        else:
            st.write("Sem IDO disponível.")
    with colB:
        st.markdown("**Vigiágua — registros**")
        st.write(f"Registros obtidos: {len(dados_parametros) if 'dados_parametros' in locals() else 0}")

    st.markdown("---")
    st.markdown("**Observações / exportação**")
    if 'dados_infodengue' in locals() and not dados_infodengue.empty:
        csv = dados_infodengue.to_csv(index=False)
        st.download_button("Exportar dados InfoDengue (CSV)", data=csv, file_name=f"infodengue_{municipio}_{ano}.csv")
    if 'dados_parametros' in locals() and not dados_parametros.empty:
        csv2 = dados_parametros.to_csv(index=False)
        st.download_button("Exportar dados Vigiágua (CSV)", data=csv2, file_name=f"vigiagua_{municipio}_{ano}.csv")

# --- Tab 4: Dados Brutos ---
with tab4:
    st.subheader("Dados brutos carregados (preview)")
    if not dados_municipio.empty:
        st.markdown("### ContaOvos — últimas contagens")
        st.dataframe(dados_municipio.head(200))
    else:
        st.info("Sem dados ContaOvos carregados.")

    if 'dados_infodengue' in locals() and not dados_infodengue.empty:
        st.markdown("### InfoDengue — dados")
        st.dataframe(dados_infodengue.head(200))
    if 'dados_parametros' in locals() and not dados_parametros.empty:
        st.markdown("### Vigiágua — parâmetros")
        st.dataframe(dados_parametros.head(200))

st.markdown("© Gerado automaticamente — ajuste e personalize conforme necessário.")


