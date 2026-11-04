from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = APP_DIR / "data" / "JS_Barbearia_Dashboard_Dados.csv"

WEEKDAY_ORDER = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]

STATUS_COLORS = {
    "Concluído": "#22c55e",
    "Confirmado": "#38bdf8",
    "Cancelado": "#f59e0b",
    "No-show": "#f43f5e",
}


st.set_page_config(
    page_title="JS Barbearia | Dashboard",
    page_icon="✂️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def brl(value: float) -> str:
    """Format a number as Brazilian currency."""
    if pd.isna(value):
        return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float) -> str:
    if pd.isna(value):
        return "0,0%"
    return f"{value:.1%}".replace(".", ",")


def safe_options(series: pd.Series) -> list[str]:
    return sorted(series.dropna().astype(str).unique().tolist())


@st.cache_data(show_spinner=False)
def load_data(path: str, uploaded_bytes: bytes | None = None) -> pd.DataFrame:
    if uploaded_bytes is not None:
        data = pd.read_csv(io.BytesIO(uploaded_bytes), encoding="utf-8-sig")
    else:
        data = pd.read_csv(path, encoding="utf-8-sig")

    data.columns = data.columns.str.strip()
    data["data"] = pd.to_datetime(data["data"], errors="coerce")
    for column in [
        "duracao_minutos",
        "preco_tabela",
        "desconto",
        "valor_total",
        "avaliacao",
    ]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data["forma_pagamento"] = data["forma_pagamento"].fillna("Não informado")
    data["mes_ano"] = data["data"].dt.to_period("M").astype(str)
    data["mes_label"] = data["data"].dt.strftime("%b/%Y").str.title()
    data["horario_ord"] = pd.to_datetime(data["horario"], format="%H:%M", errors="coerce")
    data["horario_label"] = data["horario"].astype(str)
    data["dia_semana"] = pd.Categorical(
        data["dia_semana"], categories=WEEKDAY_ORDER, ordered=True
    )
    return data.sort_values(["data", "horario_ord", "id_agendamento"]).reset_index(drop=True)


def apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros")

    min_date = data["data"].min().date()
    max_date = data["data"].max().date()
    date_range = st.sidebar.date_input(
        "Período",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        data = data[data["data"].dt.date.between(start_date, end_date)]

    def multi_filter(label: str, column: str) -> None:
        nonlocal data
        choices = st.sidebar.multiselect(label, safe_options(data[column]), default=safe_options(data[column]))
        if choices:
            data = data[data[column].astype(str).isin(choices)]

    multi_filter("Status", "status")
    multi_filter("Serviço", "servico")
    multi_filter("Categoria", "categoria_servico")
    multi_filter("Profissional", "barbeiro")
    multi_filter("Cliente recorrente", "cliente_recorrente")
    multi_filter("Faixa etária", "faixa_etaria")
    multi_filter("Bairro", "bairro")
    multi_filter("Forma de pagamento", "forma_pagamento")
    return data


def plot_layout(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=45, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dbeafe"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.16)")
    return fig


def show_agendamentos(data: pd.DataFrame) -> None:
    st.subheader("Agendamentos")
    st.caption("Acompanhe volume, situação e distribuição dos horários filtrados.")

    left, right = st.columns(2)
    with left:
        status_data = data["status"].value_counts().rename_axis("status").reset_index(name="agendamentos")
        fig = px.pie(
            status_data,
            names="status",
            values="agendamentos",
            hole=0.55,
            color="status",
            color_discrete_map=STATUS_COLORS,
            title="Situação dos agendamentos",
        )
        st.plotly_chart(plot_layout(fig, 330), width="stretch")

    with right:
        monthly = data.groupby("mes_ano", as_index=False).agg(
            agendamentos=("id_agendamento", "count"),
            realizados=("status", lambda s: (s == "Concluído").sum()),
        )
        monthly["mês"] = pd.to_datetime(monthly["mes_ano"] + "-01").dt.strftime("%b/%Y").str.title()
        fig = px.line(
            monthly,
            x="mês",
            y=["agendamentos", "realizados"],
            markers=True,
            title="Agendamentos x serviços realizados por mês",
            labels={"value": "Quantidade", "variable": "Série", "mês": "Mês"},
        )
        fig.update_traces(line_width=3)
        st.plotly_chart(plot_layout(fig, 330), width="stretch")

    st.markdown("#### Horários mais procurados")
    heat = data.pivot_table(
        index="dia_semana",
        columns="horario_label",
        values="id_agendamento",
        aggfunc="count",
        fill_value=0,
        observed=False,
    ).reindex(WEEKDAY_ORDER)
    heat = heat.reindex(sorted(heat.columns), axis=1)
    fig = go.Figure(
        go.Heatmap(
            z=heat.values,
            x=heat.columns,
            y=heat.index,
            colorscale=[[0, "#172554"], [0.5, "#2563eb"], [1, "#38bdf8"]],
            text=heat.values,
            texttemplate="%{text}",
            hovertemplate="%{y}<br>%{x}: %{z} agendamento(s)<extra></extra>",
        )
    )
    fig.update_layout(title="Distribuição por dia e horário", xaxis_title="Horário", yaxis_title="Dia")
    st.plotly_chart(plot_layout(fig, 380), width="stretch")

    st.markdown("#### Agenda detalhada")
    columns = [
        "id_agendamento",
        "data",
        "horario_label",
        "barbeiro",
        "servico",
        "cliente_nome",
        "status",
        "valor_total",
        "forma_pagamento",
    ]
    table = data.sort_values(["data", "horario_ord"])[columns].copy()
    table["data"] = table["data"].dt.strftime("%d/%m/%Y")
    table["valor_total"] = table["valor_total"].map(brl)
    table = table.rename(
        columns={
            "id_agendamento": "ID",
            "data": "Data",
            "horario_label": "Horário",
            "barbeiro": "Profissional",
            "servico": "Serviço",
            "cliente_nome": "Cliente",
            "status": "Status",
            "valor_total": "Valor",
            "forma_pagamento": "Pagamento",
        }
    )
    st.dataframe(table, width="stretch", height=430, hide_index=True)


def show_services(data: pd.DataFrame) -> None:
    st.subheader("Serviços realizados")
    st.caption("Volume, faturamento e duração dos serviços concluídos.")
    completed = data[data["status"] == "Concluído"].copy()
    if completed.empty:
        st.info("Não há serviços concluídos no recorte atual.")
        return

    summary = completed.groupby("servico", as_index=False).agg(
        realizados=("id_agendamento", "count"),
        receita=("valor_total", "sum"),
        ticket_medio=("valor_total", "mean"),
        duracao_media=("duracao_minutos", "mean"),
    ).sort_values("realizados", ascending=False)

    left, right = st.columns(2)
    with left:
        fig = px.bar(
            summary.sort_values("realizados"),
            x="realizados",
            y="servico",
            orientation="h",
            text="realizados",
            title="Quantidade de serviços realizados",
            labels={"realizados": "Serviços", "servico": "Serviço"},
            color="realizados",
            color_continuous_scale="Blues",
        )
        st.plotly_chart(plot_layout(fig, 390), width="stretch")
    with right:
        fig = px.bar(
            summary.sort_values("receita"),
            x="receita",
            y="servico",
            orientation="h",
            text_auto=".2s",
            title="Receita por serviço realizado",
            labels={"receita": "Receita (R$)", "servico": "Serviço"},
            color="receita",
            color_continuous_scale="Tealgrn",
        )
        st.plotly_chart(plot_layout(fig, 390), width="stretch")

    category = completed.groupby("categoria_servico", as_index=False).agg(
        realizados=("id_agendamento", "count"), receita=("valor_total", "sum")
    )
    fig = px.bar(
        category.sort_values("receita"),
        x="categoria_servico",
        y="receita",
        text_auto=".2s",
        title="Receita por categoria de serviço",
        labels={"categoria_servico": "Categoria", "receita": "Receita (R$)"},
        color="categoria_servico",
    )
    st.plotly_chart(plot_layout(fig, 340), width="stretch")

    table = summary.rename(
        columns={
            "servico": "Serviço",
            "realizados": "Realizados",
            "receita": "Receita",
            "ticket_medio": "Ticket médio",
            "duracao_media": "Duração média (min)",
        }
    ).copy()
    for col in ["Receita", "Ticket médio"]:
        table[col] = table[col].map(brl)
    table["Duração média (min)"] = table["Duração média (min)"].round(1)
    st.dataframe(table, width="stretch", hide_index=True)


def show_clients(data: pd.DataFrame) -> None:
    st.subheader("Perfil e frequência dos clientes")
    st.caption("Entenda quem frequenta a barbearia e quantas vezes cada cliente retorna.")

    client_freq = data.groupby(["cliente_id", "cliente_nome"], as_index=False).agg(
        agendamentos=("id_agendamento", "count"),
        receita=("valor_total", "sum"),
        recorrente=("cliente_recorrente", lambda s: "Sim" if (s == "Sim").any() else "Não"),
    )
    recurring_rate = (data["cliente_recorrente"] == "Sim").mean()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Clientes únicos", f"{data['cliente_id'].nunique():,}".replace(",", "."))
    k2.metric("Clientes recorrentes", f"{(data['cliente_recorrente'] == 'Sim').sum():,}".replace(",", "."))
    k3.metric("Taxa de recorrência", pct(recurring_rate))
    k4.metric("Média de agendamentos/cliente", f"{client_freq['agendamentos'].mean():.1f}".replace(".", ","))

    left, right = st.columns(2)
    with left:
        age = data["faixa_etaria"].value_counts().rename_axis("faixa_etaria").reset_index(name="agendamentos")
        age["ord"] = age["faixa_etaria"].map({"18-24": 1, "25-34": 2, "35-44": 3, "45-54": 4, "55+": 5})
        age = age.sort_values("ord")
        fig = px.bar(age, x="faixa_etaria", y="agendamentos", text="agendamentos", title="Agendamentos por faixa etária")
        st.plotly_chart(plot_layout(fig, 330), width="stretch")
    with right:
        neighborhood = data["bairro"].value_counts().rename_axis("bairro").reset_index(name="agendamentos")
        fig = px.bar(
            neighborhood.sort_values("agendamentos"),
            x="agendamentos",
            y="bairro",
            orientation="h",
            text="agendamentos",
            title="Origem dos clientes por bairro",
            color="agendamentos",
            color_continuous_scale="Purples",
        )
        st.plotly_chart(plot_layout(fig, 330), width="stretch")

    frequency = client_freq["agendamentos"].value_counts().rename_axis("vezes").reset_index(name="clientes")
    frequency = frequency.sort_values("vezes")
    fig = px.bar(
        frequency,
        x="vezes",
        y="clientes",
        text="clientes",
        title="Frequência: quantos clientes agendaram 1, 2, 3... vezes",
        labels={"vezes": "Agendamentos por cliente", "clientes": "Clientes"},
    )
    st.plotly_chart(plot_layout(fig, 330), width="stretch")

    st.markdown("#### Clientes com maior frequência")
    top_clients = client_freq.sort_values(["agendamentos", "receita"], ascending=False).head(15).copy()
    top_clients["receita"] = top_clients["receita"].map(brl)
    top_clients = top_clients.rename(
        columns={
            "cliente_nome": "Cliente",
            "agendamentos": "Agendamentos",
            "receita": "Receita movimentada",
            "recorrente": "Recorrente",
        }
    )[["Cliente", "Agendamentos", "Receita movimentada", "Recorrente"]]
    st.dataframe(top_clients, width="stretch", hide_index=True)


def show_professionals(data: pd.DataFrame) -> None:
    st.subheader("Desempenho dos profissionais")
    st.caption("Compare volume, conclusão, faturamento, ticket e avaliações.")
    performance = data.groupby("barbeiro", as_index=False).agg(
        agendamentos=("id_agendamento", "count"),
        realizados=("status", lambda s: (s == "Concluído").sum()),
        cancelados=("status", lambda s: (s == "Cancelado").sum()),
        no_show=("status", lambda s: (s == "No-show").sum()),
        receita=("valor_total", lambda s: data.loc[s.index][data.loc[s.index, "status"] == "Concluído"]["valor_total"].sum()),
        avaliacao_media=("avaliacao", "mean"),
    )
    performance["taxa_conclusao"] = performance["realizados"] / performance["agendamentos"].where(performance["agendamentos"] > 0)
    performance["ticket_medio"] = performance["receita"] / performance["realizados"].where(performance["realizados"] > 0)
    performance = performance.sort_values("receita", ascending=False)

    left, right = st.columns(2)
    with left:
        fig = px.bar(
            performance,
            x="barbeiro",
            y="receita",
            text_auto=".2s",
            title="Receita concluída por profissional",
            labels={"barbeiro": "Profissional", "receita": "Receita (R$)"},
            color="receita",
            color_continuous_scale="Tealgrn",
        )
        st.plotly_chart(plot_layout(fig, 330), width="stretch")
    with right:
        fig = px.bar(
            performance,
            x="barbeiro",
            y="taxa_conclusao",
            text=performance["taxa_conclusao"].map(pct),
            title="Taxa de conclusão",
            labels={"barbeiro": "Profissional", "taxa_conclusao": "Taxa"},
            color="taxa_conclusao",
            color_continuous_scale="Blues",
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(plot_layout(fig, 330), width="stretch")

    table = performance.rename(
        columns={
            "barbeiro": "Profissional",
            "agendamentos": "Agendamentos",
            "realizados": "Realizados",
            "cancelados": "Cancelados",
            "no_show": "No-show",
            "receita": "Receita",
            "avaliacao_media": "Avaliação média",
            "taxa_conclusao": "Taxa de conclusão",
            "ticket_medio": "Ticket médio",
        }
    ).copy()
    table["Receita"] = table["Receita"].map(brl)
    table["Ticket médio"] = table["Ticket médio"].map(brl)
    table["Avaliação média"] = table["Avaliação média"].round(2)
    table["Taxa de conclusão"] = table["Taxa de conclusão"].map(pct)
    st.dataframe(table, width="stretch", hide_index=True)


def show_indicators(data: pd.DataFrame) -> None:
    st.subheader("Indicadores de desempenho")
    st.caption("Indicadores calculados diretamente a partir dos agendamentos filtrados.")
    monthly = data.groupby("mes_ano", as_index=False).agg(
        agendamentos=("id_agendamento", "count"),
        realizados=("status", lambda s: (s == "Concluído").sum()),
        no_show=("status", lambda s: (s == "No-show").sum()),
        receita=("valor_total", lambda s: data.loc[s.index][data.loc[s.index, "status"] == "Concluído"]["valor_total"].sum()),
        avaliacao_media=("avaliacao", "mean"),
    )
    monthly["taxa_conclusao"] = monthly["realizados"] / monthly["agendamentos"].where(monthly["agendamentos"] > 0)
    monthly["taxa_no_show"] = monthly["no_show"] / monthly["agendamentos"].where(monthly["agendamentos"] > 0)
    monthly["ticket_medio"] = monthly["receita"] / monthly["realizados"].where(monthly["realizados"] > 0)
    monthly["mês"] = pd.to_datetime(monthly["mes_ano"] + "-01").dt.strftime("%b/%Y").str.title()

    left, right = st.columns(2)
    with left:
        fig = px.line(
            monthly,
            x="mês",
            y=["taxa_conclusao", "taxa_no_show"],
            markers=True,
            title="Taxa de conclusão e no-show",
            labels={"value": "Taxa", "variable": "Indicador", "mês": "Mês"},
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(plot_layout(fig, 350), width="stretch")
    with right:
        fig = px.bar(
            monthly,
            x="mês",
            y="receita",
            text_auto=".2s",
            title="Receita concluída por mês",
            labels={"mês": "Mês", "receita": "Receita (R$)"},
            color="receita",
            color_continuous_scale="Tealgrn",
        )
        st.plotly_chart(plot_layout(fig, 350), width="stretch")

    indicator_table = monthly[
        ["mês", "agendamentos", "realizados", "taxa_conclusao", "taxa_no_show", "receita", "ticket_medio", "avaliacao_media"]
    ].rename(
        columns={
            "mês": "Mês",
            "agendamentos": "Agendamentos",
            "realizados": "Realizados",
            "taxa_conclusao": "Taxa de conclusão",
            "taxa_no_show": "Taxa de no-show",
            "receita": "Receita",
            "ticket_medio": "Ticket médio",
            "avaliacao_media": "Avaliação média",
        }
    ).copy()
    indicator_table["Taxa de conclusão"] = indicator_table["Taxa de conclusão"].map(pct)
    indicator_table["Taxa de no-show"] = indicator_table["Taxa de no-show"].map(pct)
    indicator_table["Receita"] = indicator_table["Receita"].map(brl)
    indicator_table["Ticket médio"] = indicator_table["Ticket médio"].map(brl)
    indicator_table["Avaliação média"] = indicator_table["Avaliação média"].round(2)
    st.dataframe(indicator_table, width="stretch", hide_index=True)


def main() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #07111f; color: #e2e8f0; }
        [data-testid="stSidebar"] { background: #0b1728; }
        [data-testid="stMetric"] { background: linear-gradient(135deg, #102b4a, #0c1e35); border: 1px solid #1e446b; padding: 15px; border-radius: 14px; }
        [data-testid="stMetricLabel"] { color: #93c5fd; }
        h1, h2, h3 { color: #f8fafc; }
        .block-container { padding-top: 2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("✂️ JS Barbearia")
    st.markdown("### Dashboard operacional e comercial")

    uploaded = st.sidebar.file_uploader("Trocar arquivo CSV", type=["csv"])
    if uploaded is not None:
        raw = uploaded.getvalue()
        data = load_data(str(DEFAULT_CSV), raw)
        source_label = uploaded.name
    elif DEFAULT_CSV.exists():
        data = load_data(str(DEFAULT_CSV))
        source_label = DEFAULT_CSV.name
    else:
        st.error("Arquivo CSV não encontrado. Use o carregador na barra lateral.")
        st.stop()

    st.sidebar.caption(f"Fonte: {source_label}")
    st.sidebar.caption(f"Registros no arquivo: {len(data):,}".replace(",", "."))
    filtered = apply_filters(data)

    if filtered.empty:
        st.warning("Nenhum agendamento corresponde aos filtros selecionados.")
        st.stop()

    st.sidebar.divider()
    st.sidebar.download_button(
        "Baixar dados filtrados",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name="agendamentos_filtrados.csv",
        mime="text/csv",
    )

    completed = filtered[filtered["status"] == "Concluído"]
    revenue = completed["valor_total"].sum()
    ticket = completed["valor_total"].mean() if not completed.empty else 0
    completion_rate = len(completed) / len(filtered)
    no_show_count = (filtered["status"] == "No-show").sum()

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Agendamentos", f"{len(filtered):,}".replace(",", "."))
    k2.metric("Serviços realizados", f"{len(completed):,}".replace(",", "."))
    k3.metric("Receita concluída", brl(revenue))
    k4.metric("Ticket médio", brl(ticket))
    k5.metric("Taxa de conclusão", pct(completion_rate))
    k6.metric("No-show", f"{no_show_count:,}".replace(",", "."))
    st.caption(f"Exibindo {len(filtered):,} de {len(data):,} registros do arquivo após os filtros.".replace(",", "."))

    tabs = st.tabs([
        "Agendamentos",
        "Serviços realizados",
        "Perfil e frequência",
        "Profissionais",
        "Indicadores",
    ])
    with tabs[0]:
        show_agendamentos(filtered)
    with tabs[1]:
        show_services(filtered)
    with tabs[2]:
        show_clients(filtered)
    with tabs[3]:
        show_professionals(filtered)
    with tabs[4]:
        show_indicators(filtered)


if __name__ == "__main__":
    main()
