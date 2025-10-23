import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px

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

# Variáveis para evitar erro antes do clique
dados_municipio = pd.DataFrame()
dados_infodengue = pd.DataFrame()
dados_parametros = pd.DataFrame()

if atualizar:
    with st.spinner("Carregando dados das APIs..."):
        dados_municipio = get_last_counting_public(municipio)
        dados_infodengue = buscar_dados_dengue(municipio, 1, 52, ano, ano, cod_ibge7_rs_dict)
        dados_parametros = buscar_parametros_sisagua(municipio, ano, cod_ibge7_rs_dict)
    st.success("✅ Dados atualizados com sucesso!")

# ---------- Tabs ----------
tab1, tab2, tab3, tab4 = st.tabs(["Dengue (ContaOvos + InfoDengue)", "Vigiágua (SisÁgua)", "Resumo", "Dados Brutos"])

if not atualizar:
    st.info("👈 Selecione o município e o ano, depois clique em **Atualizar / Recarregar** para carregar os dados.")
else:
    'ola'
