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

AGE_GROUP_ORDER = ["18-24", "25-34", "35-44", "45-54", "55+"]

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


def format_int(value: int | float) -> str:
    """Format an integer using Brazilian thousands separators."""
    return f"{int(value):,}".replace(",", ".")


def safe_options(series: pd.Series) -> list[str]:
    return sorted(series.dropna().astype(str).unique().tolist())


def compute_kpis(data: pd.DataFrame) -> dict[str, float]:
    """Compute core operational and financial KPIs for the filtered dataset."""
    completed = data[data["status"] == "Concluído"]
    lost = data[data["status"].isin(["Cancelado", "No-show"])]
    confirmed = data[data["status"] == "Confirmado"]

    revenue = float(completed["valor_total"].sum())
    total_hours = float(completed["duracao_minutos"].sum()) / 60.0
    table_completed = float(completed["preco_tabela"].sum())
    discounts = float(completed["desconto"].sum())

    return {
        "total": float(len(data)),
        "completed_count": float(len(completed)),
        "revenue": revenue,
        "ticket": float(completed["valor_total"].mean()) if not completed.empty else 0.0,
        "completion_rate": len(completed) / len(data) if len(data) > 0 else 0.0,
        "no_show_count": float((data["status"] == "No-show").sum()),
        "predicted_revenue": float(confirmed["valor_total"].sum()),
        "lost_revenue": float(lost["preco_tabela"].sum()),
        "discounts": discounts,
        "discount_rate": discounts / table_completed if table_completed > 0 else 0.0,
        "total_hours": total_hours,
        "revenue_per_hour": revenue / total_hours if total_hours > 0 else 0.0,
    }


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

    data["servico"] = data["servico"].replace({"Sombrancelha": "Sobrancelha"})
    data["forma_pagamento"] = data["forma_pagamento"].fillna("Não informado")
    data["mes_ano"] = data["data"].dt.to_period("M").astype(str)
    data["mes_label"] = data["data"].dt.strftime("%b/%Y").str.title()
    data["horario_ord"] = pd.to_datetime(data["horario"], format="%H:%M", errors="coerce")
    data["horario_label"] = data["horario"].astype(str)
    data["hora"] = (
        data["horario_ord"].dt.strftime("%Hh").fillna(data["horario_label"].str.slice(0, 2) + "h")
    )
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
    has_legend = len(fig.data) > 1 or any(
        getattr(trace, "type", None) == "pie" for trace in fig.data
    )
    top_margin = 95 if has_legend else 72
    fig.update_layout(
        height=height + 40,
        margin=dict(l=16, r=24, t=top_margin, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dbeafe"),
        title=dict(y=0.97, yanchor="top", x=0, xanchor="left"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title_text="",
        ),
    )
    fig.update_xaxes(showgrid=False, automargin=True)
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.16)", automargin=True)
    fig.update_traces(cliponaxis=False, selector=dict(type="bar"))
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

    st.markdown("#### Faltas e cancelamentos por dia e horário")
    left, right = st.columns(2)
    with left:
        weekday_loss = (
            data.groupby("dia_semana", observed=False, as_index=False)
            .agg(
                agendamentos=("id_agendamento", "count"),
                cancelado=("status", lambda s: (s == "Cancelado").sum()),
                no_show=("status", lambda s: (s == "No-show").sum()),
            )
        )
        weekday_loss["taxa_cancelado"] = weekday_loss["cancelado"] / weekday_loss["agendamentos"].where(
            weekday_loss["agendamentos"] > 0
        )
        weekday_loss["taxa_no_show"] = weekday_loss["no_show"] / weekday_loss["agendamentos"].where(
            weekday_loss["agendamentos"] > 0
        )
        weekday_melted = weekday_loss.melt(
            id_vars="dia_semana",
            value_vars=["taxa_cancelado", "taxa_no_show"],
            var_name="Tipo",
            value_name="Taxa",
        )
        weekday_melted["Tipo"] = weekday_melted["Tipo"].map(
            {"taxa_cancelado": "Cancelado", "taxa_no_show": "No-show"}
        )
        fig = px.bar(
            weekday_melted,
            x="dia_semana",
            y="Taxa",
            color="Tipo",
            barmode="stack",
            color_discrete_map=STATUS_COLORS,
            title="Taxa de cancelamento e no-show por dia",
            labels={"dia_semana": "Dia da semana", "Taxa": "Taxa"},
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(plot_layout(fig, 340), width="stretch")

    with right:
        hour_loss = (
            data.groupby("hora", as_index=False)
            .agg(
                agendamentos=("id_agendamento", "count"),
                faltas=("status", lambda s: s.isin(["Cancelado", "No-show"]).sum()),
            )
            .sort_values("hora")
        )
        hour_loss["taxa_falta"] = hour_loss["faltas"] / hour_loss["agendamentos"].where(
            hour_loss["agendamentos"] > 0
        )
        fig = px.bar(
            hour_loss,
            x="hora",
            y="taxa_falta",
            text=hour_loss["taxa_falta"].map(pct),
            title="Taxa de perdas (Cancel. + No-show) por hora",
            labels={"hora": "Faixa horária", "taxa_falta": "Taxa de perdas"},
            color="taxa_falta",
            color_continuous_scale="OrRd",
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(plot_layout(fig, 340), width="stretch")

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

    summary = completed.groupby(["servico", "categoria_servico"], as_index=False).agg(
        realizados=("id_agendamento", "count"),
        receita=("valor_total", "sum"),
        ticket_medio=("valor_total", "mean"),
        duracao_media=("duracao_minutos", "mean"),
        duracao_total=("duracao_minutos", "sum"),
        descontos=("desconto", "sum"),
        preco_tabela=("preco_tabela", "sum"),
    ).sort_values("realizados", ascending=False)
    summary["receita_hora"] = summary["receita"] / (summary["duracao_total"] / 60.0).where(
        summary["duracao_total"] > 0
    )

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

    left, right = st.columns(2)
    with left:
        fig = px.bar(
            summary.sort_values("receita_hora"),
            x="receita_hora",
            y="servico",
            orientation="h",
            text=summary.sort_values("receita_hora")["receita_hora"].map(brl),
            title="Rentabilidade por hora de cadeira (R$/hora)",
            labels={"receita_hora": "Receita por hora (R$/h)", "servico": "Serviço"},
            color="receita_hora",
            color_continuous_scale="Emrld",
        )
        st.plotly_chart(plot_layout(fig, 390), width="stretch")
    with right:
        fig = px.scatter(
            summary,
            x="duracao_media",
            y="receita_hora",
            size="realizados",
            color="categoria_servico",
            hover_name="servico",
            title="Duração média x Receita por hora",
            labels={
                "duracao_media": "Duração média (min)",
                "receita_hora": "Receita por hora (R$/h)",
                "categoria_servico": "Categoria",
                "realizados": "Realizados",
            },
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

    service_age = (
        completed.groupby(["servico", "faixa_etaria"], observed=False)
        .size()
        .unstack(fill_value=0)
        .reindex(index=summary["servico"], columns=AGE_GROUP_ORDER, fill_value=0)
    )
    fig = px.imshow(
        service_age,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="Blues",
        title="Serviços realizados por faixa etária",
        labels={"x": "Faixa etária", "y": "Serviço", "color": "Realizados"},
    )
    st.plotly_chart(plot_layout(fig, 420), width="stretch")

    table = summary[
        [
            "servico",
            "categoria_servico",
            "realizados",
            "receita",
            "ticket_medio",
            "duracao_media",
            "receita_hora",
            "descontos",
        ]
    ].rename(
        columns={
            "servico": "Serviço",
            "categoria_servico": "Categoria",
            "realizados": "Realizados",
            "receita": "Receita",
            "ticket_medio": "Ticket médio",
            "duracao_media": "Duração média (min)",
            "receita_hora": "Receita/hora",
            "descontos": "Descontos",
        }
    ).copy()
    for col in ["Receita", "Ticket médio", "Receita/hora", "Descontos"]:
        table[col] = table[col].map(brl)
    table["Duração média (min)"] = table["Duração média (min)"].round(1)
    st.dataframe(table, width="stretch", hide_index=True)


def compute_client_metrics(data: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | None]]:
    """Compute per-client frequency, LTV, recency, and aggregate retention KPIs."""
    work = data.assign(
        receita_concluida=data["valor_total"].where(data["status"] == "Concluído", 0.0)
    )
    client_freq = work.groupby(["cliente_id", "cliente_nome"], as_index=False).agg(
        agendamentos=("id_agendamento", "count"),
        concluidos=("status", lambda s: (s == "Concluído").sum()),
        receita=("receita_concluida", "sum"),
        ultima_visita=("data", "max"),
        recorrente=("cliente_recorrente", lambda s: "Sim" if (s == "Sim").any() else "Não"),
    )
    ref_date = data["data"].max()
    client_freq["dias_sem_visita"] = (ref_date - client_freq["ultima_visita"]).dt.days

    ordered = data.sort_values(["cliente_id", "data"])
    gaps = ordered.groupby("cliente_id")["data"].diff().dt.days.dropna()

    unique_clients = len(client_freq)
    returning_clients = int((client_freq["agendamentos"] >= 2).sum())
    inactive_60 = int((client_freq["dias_sem_visita"] > 60).sum())

    summary = {
        "unique_clients": float(unique_clients),
        "returning_clients": float(returning_clients),
        "retention_rate": returning_clients / unique_clients if unique_clients > 0 else 0.0,
        "avg_visits": float(client_freq["agendamentos"].mean()) if unique_clients > 0 else 0.0,
        "ltv_avg": float(client_freq["receita"].mean()) if unique_clients > 0 else 0.0,
        "avg_return_days": float(gaps.mean()) if not gaps.empty else None,
        "inactive_60": float(inactive_60),
        "inactive_rate": inactive_60 / unique_clients if unique_clients > 0 else 0.0,
    }
    return client_freq, summary


def show_clients(data: pd.DataFrame) -> None:
    st.subheader("Perfil, frequência e retenção dos clientes")
    st.caption("Entenda quem frequenta a barbearia, quanto cada cliente gera (LTV) e o ritmo de retorno.")

    client_freq, metrics = compute_client_metrics(data)
    avg_days_label = (
        f"{metrics['avg_return_days']:.0f} dias"
        if metrics["avg_return_days"] is not None
        else "N/D"
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Clientes únicos", format_int(metrics["unique_clients"]))
    k2.metric("Clientes que retornaram (≥ 2x)", format_int(metrics["returning_clients"]))
    k3.metric("Taxa de retenção real", pct(metrics["retention_rate"] or 0.0))
    k4.metric("Média de visitas/cliente", f"{metrics['avg_visits']:.1f}".replace(".", ","))

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("LTV médio (receita/cliente)", brl(metrics["ltv_avg"] or 0.0))
    r2.metric("Intervalo médio de retorno", avg_days_label)
    r3.metric("Inativos (> 60 dias no período)", format_int(metrics["inactive_60"]))
    r4.metric("% de clientes inativos (> 60d)", pct(metrics["inactive_rate"] or 0.0))

    left, right = st.columns(2)
    with left:
        age = data["faixa_etaria"].value_counts().rename_axis("faixa_etaria").reset_index(name="agendamentos")
        age["ord"] = age["faixa_etaria"].map({label: idx for idx, label in enumerate(AGE_GROUP_ORDER, start=1)})
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

    left, right = st.columns(2)
    with left:
        completed = data[data["status"] == "Concluído"]
        age_rev = (
            completed.groupby("faixa_etaria", as_index=False)
            .agg(receita=("valor_total", "sum"), ticket=("valor_total", "mean"))
        )
        age_rev["ord"] = age_rev["faixa_etaria"].map(
            {label: idx for idx, label in enumerate(AGE_GROUP_ORDER, start=1)}
        )
        age_rev = age_rev.sort_values("ord")
        fig = px.bar(
            age_rev,
            x="faixa_etaria",
            y="receita",
            text=age_rev["receita"].map(brl),
            title="Receita concluída por faixa etária",
            labels={"faixa_etaria": "Faixa etária", "receita": "Receita (R$)"},
            color="ticket",
            color_continuous_scale="Tealgrn",
        )
        st.plotly_chart(plot_layout(fig, 330), width="stretch")
    with right:
        recency_labels = ["0-30 dias", "31-60 dias", "61-90 dias", "90+ dias"]
        recency_series = pd.cut(
            client_freq["dias_sem_visita"],
            bins=[-1, 30, 60, 90, float("inf")],
            labels=recency_labels,
        )
        recency = (
            recency_series.value_counts()
            .reindex(recency_labels, fill_value=0)
            .rename_axis("faixa_recencia")
            .reset_index(name="clientes")
        )
        fig = px.bar(
            recency,
            x="faixa_recencia",
            y="clientes",
            text="clientes",
            title="Recência: dias desde o último agendamento",
            labels={"faixa_recencia": "Tempo sem visitar", "clientes": "Clientes"},
            color="clientes",
            color_continuous_scale="Blues",
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

    st.markdown("#### Clientes com maior frequência e valor (LTV)")
    top_clients = client_freq.sort_values(["receita", "agendamentos"], ascending=False).head(15).copy()
    top_clients["receita"] = top_clients["receita"].map(brl)
    top_clients["ultima_visita"] = top_clients["ultima_visita"].dt.strftime("%d/%m/%Y")
    top_clients = top_clients.rename(
        columns={
            "cliente_nome": "Cliente",
            "agendamentos": "Agendamentos",
            "concluidos": "Concluídos",
            "receita": "Receita concluída (LTV)",
            "ultima_visita": "Última visita",
            "dias_sem_visita": "Dias sem visita",
            "recorrente": "Recorrente",
        }
    )[["Cliente", "Agendamentos", "Concluídos", "Receita concluída (LTV)", "Última visita", "Dias sem visita", "Recorrente"]]
    st.dataframe(top_clients, width="stretch", hide_index=True)


def show_professionals(data: pd.DataFrame) -> None:
    st.subheader("Desempenho dos profissionais")
    st.caption("Compare volume, conclusão, faturamento, produtividade por hora, perdas e avaliações.")

    work = data.assign(
        receita_concluida=data["valor_total"].where(data["status"] == "Concluído", 0.0),
        receita_perdida=data["preco_tabela"].where(data["status"].isin(["Cancelado", "No-show"]), 0.0),
        minutos_concluidos=data["duracao_minutos"].where(data["status"] == "Concluído", 0.0),
    )
    performance = work.groupby("barbeiro", as_index=False).agg(
        agendamentos=("id_agendamento", "count"),
        realizados=("status", lambda s: (s == "Concluído").sum()),
        cancelados=("status", lambda s: (s == "Cancelado").sum()),
        no_show=("status", lambda s: (s == "No-show").sum()),
        receita=("receita_concluida", "sum"),
        receita_perdida=("receita_perdida", "sum"),
        horas_trabalhadas=("minutos_concluidos", lambda s: s.sum() / 60.0),
        avaliacao_media=("avaliacao", "mean"),
        taxa_avaliacao=("avaliacao", lambda s: s.notna().mean()),
    )
    performance["taxa_conclusao"] = performance["realizados"] / performance["agendamentos"].where(
        performance["agendamentos"] > 0
    )
    performance["ticket_medio"] = performance["receita"] / performance["realizados"].where(
        performance["realizados"] > 0
    )
    performance["receita_hora"] = performance["receita"] / performance["horas_trabalhadas"].where(
        performance["horas_trabalhadas"] > 0
    )
    performance = performance.sort_values("receita", ascending=False)

    if len(performance) == 1:
        st.info(
            "A base filtrada possui apenas 1 profissional no momento. "
            "Ao adicionar novos barbeiros no CSV, esta aba compara todos automaticamente."
        )

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

    table = performance[
        [
            "barbeiro",
            "agendamentos",
            "realizados",
            "cancelados",
            "no_show",
            "receita",
            "receita_perdida",
            "horas_trabalhadas",
            "receita_hora",
            "ticket_medio",
            "taxa_conclusao",
            "avaliacao_media",
            "taxa_avaliacao",
        ]
    ].rename(
        columns={
            "barbeiro": "Profissional",
            "agendamentos": "Agendamentos",
            "realizados": "Realizados",
            "cancelados": "Cancelados",
            "no_show": "No-show",
            "receita": "Receita",
            "receita_perdida": "Receita perdida",
            "horas_trabalhadas": "Horas trabalhadas",
            "receita_hora": "Receita/hora",
            "ticket_medio": "Ticket médio",
            "taxa_conclusao": "Taxa de conclusão",
            "avaliacao_media": "Avaliação média",
            "taxa_avaliacao": "Taxa de avaliação",
        }
    ).copy()
    for col in ["Receita", "Receita perdida", "Receita/hora", "Ticket médio"]:
        table[col] = table[col].map(brl)
    table["Horas trabalhadas"] = table["Horas trabalhadas"].round(1)
    table["Avaliação média"] = table["Avaliação média"].round(2)
    table["Taxa de conclusão"] = table["Taxa de conclusão"].map(pct)
    table["Taxa de avaliação"] = table["Taxa de avaliação"].map(pct)
    st.dataframe(table, width="stretch", hide_index=True)


def build_insights(data: pd.DataFrame) -> list[str]:
    """Generate dynamic executive insights from the filtered dataset."""
    insights: list[str] = []
    kpis = compute_kpis(data)
    completed = data[data["status"] == "Concluído"]

    if not completed.empty:
        svc = completed.groupby("servico", as_index=False).agg(
            realizados=("id_agendamento", "count"),
            receita=("valor_total", "sum"),
            minutos=("duracao_minutos", "sum"),
        )
        svc["receita_hora"] = svc["receita"] / (svc["minutos"] / 60.0).where(svc["minutos"] > 0)
        top_vol = svc.sort_values("realizados", ascending=False).iloc[0]
        top_hour = svc.sort_values("receita_hora", ascending=False).iloc[0]
        insights.append(
            f"**Serviços:** **{top_vol['servico']}** lidera em volume ({format_int(top_vol['realizados'])} atendimentos), "
            f"enquanto **{top_hour['servico']}** apresenta maior rentabilidade por tempo ({brl(top_hour['receita_hora'])}/hora)."
        )

    day_counts = data.groupby("dia_semana", observed=False)["id_agendamento"].count()
    if not day_counts.empty and day_counts.max() > 0:
        peak_day = day_counts.idxmax()
        peak_hour = data["hora"].value_counts().idxmax()
        loss_by_day = (
            data.assign(perda=data["status"].isin(["Cancelado", "No-show"]))
            .groupby("dia_semana", observed=False)["perda"]
            .mean()
        )
        worst_loss_day = loss_by_day.idxmax()
        insights.append(
            f"**Demanda e faltas:** O maior movimento ocorre em **{peak_day}** (pico às **{peak_hour}**). "
            f"A maior taxa de cancelamento/no-show aparece em **{worst_loss_day}** ({pct(float(loss_by_day.loc[worst_loss_day]))})."
        )

    insights.append(
        f"**Impacto financeiro:** Além de **{brl(kpis['revenue'])}** concluídos e **{brl(kpis['predicted_revenue'])}** "
        f"previstos em confirmados, **{brl(kpis['lost_revenue'])}** deixaram de entrar por cancelamentos/no-show "
        f"e **{brl(kpis['discounts'])}** foram concedidos em descontos ({pct(kpis['discount_rate'])} do valor de tabela)."
    )

    _, client_metrics = compute_client_metrics(data)
    avg_days = (
        f" a cada **{client_metrics['avg_return_days']:.0f} dias** em média"
        if client_metrics["avg_return_days"] is not None
        else ""
    )
    insights.append(
        f"**Retenção e valor (LTV):** **{pct(client_metrics['retention_rate'] or 0.0)}** dos clientes retornaram ao menos uma vez"
        f"{avg_days}, gerando LTV médio de **{brl(client_metrics['ltv_avg'] or 0.0)}** por cliente único."
    )

    rated = data["avaliacao"].dropna()
    if not rated.empty:
        resp_rate = len(rated) / len(data)
        insights.append(
            f"**Qualidade percebida:** Média de **{rated.mean():.2f}/5,0** com taxa de resposta de **{pct(resp_rate)}** "
            f"({format_int(len(rated))} avaliações registradas)."
        )
    return insights


def show_indicators(data: pd.DataFrame) -> None:
    st.subheader("Indicadores de desempenho e insights")
    st.caption("Análise financeira, eficiência operacional, projeção mensal e síntese executiva.")

    insights = build_insights(data)
    if insights:
        st.markdown("#### Resumo executivo (Storytelling automático)")
        st.info("\n".join(f"- {item}" for item in insights))

    work = data.assign(
        receita_concluida=data["valor_total"].where(data["status"] == "Concluído", 0.0),
        receita_perdida=data["preco_tabela"].where(data["status"].isin(["Cancelado", "No-show"]), 0.0),
        desconto_concluido=data["desconto"].where(data["status"] == "Concluído", 0.0),
        minutos_concluidos=data["duracao_minutos"].where(data["status"] == "Concluído", 0.0),
    )
    monthly = work.groupby("mes_ano", as_index=False).agg(
        agendamentos=("id_agendamento", "count"),
        realizados=("status", lambda s: (s == "Concluído").sum()),
        no_show=("status", lambda s: (s == "No-show").sum()),
        receita=("receita_concluida", "sum"),
        receita_perdida=("receita_perdida", "sum"),
        descontos=("desconto_concluido", "sum"),
        horas_trabalhadas=("minutos_concluidos", lambda s: s.sum() / 60.0),
        avaliacao_media=("avaliacao", "mean"),
    ).sort_values("mes_ano")
    monthly["taxa_conclusao"] = monthly["realizados"] / monthly["agendamentos"].where(monthly["agendamentos"] > 0)
    monthly["taxa_no_show"] = monthly["no_show"] / monthly["agendamentos"].where(monthly["agendamentos"] > 0)
    monthly["ticket_medio"] = monthly["receita"] / monthly["realizados"].where(monthly["realizados"] > 0)
    monthly["receita_hora"] = monthly["receita"] / monthly["horas_trabalhadas"].where(monthly["horas_trabalhadas"] > 0)
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

    left, right = st.columns(2)
    with left:
        rev_comp = monthly.melt(
            id_vars="mês",
            value_vars=["receita", "receita_perdida"],
            var_name="Série",
            value_name="Valor",
        )
        rev_comp["Série"] = rev_comp["Série"].map(
            {"receita": "Receita concluída", "receita_perdida": "Receita perdida (Cancel. + No-show)"}
        )
        fig = px.bar(
            rev_comp,
            x="mês",
            y="Valor",
            color="Série",
            barmode="group",
            color_discrete_map={
                "Receita concluída": "#22c55e",
                "Receita perdida (Cancel. + No-show)": "#f43f5e",
            },
            title="Receita concluída x Receita perdida por mês",
            labels={"mês": "Mês", "Valor": "Valor (R$)"},
        )
        st.plotly_chart(plot_layout(fig, 360), width="stretch")

    with right:
        completed = data[data["status"] == "Concluído"]
        if completed.empty:
            st.info("Não há receitas concluídas por forma de pagamento no recorte atual.")
        else:
            payment = (
                completed.groupby("forma_pagamento", as_index=False)
                .agg(receita=("valor_total", "sum"), atendimentos=("id_agendamento", "count"))
                .sort_values("receita")
            )
            fig = px.bar(
                payment,
                x="receita",
                y="forma_pagamento",
                orientation="h",
                text=payment["receita"].map(brl),
                title="Receita por forma de pagamento",
                labels={"forma_pagamento": "Forma de pagamento", "receita": "Receita (R$)"},
                color="receita",
                color_continuous_scale="Blues",
            )
            st.plotly_chart(plot_layout(fig, 360), width="stretch")

    left, right = st.columns(2)
    with left:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=monthly["mês"],
                y=monthly["receita"],
                mode="lines+markers",
                name="Receita realizada",
                line=dict(color="#38bdf8", width=3),
            )
        )
        if len(monthly) >= 2:
            monthly["media_movel_3m"] = monthly["receita"].rolling(window=3, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=monthly["mês"],
                    y=monthly["media_movel_3m"],
                    mode="lines",
                    name="Média móvel (3M)",
                    line=dict(color="#22c55e", width=2, dash="dot"),
                )
            )
            xs = list(range(len(monthly)))
            ys = monthly["receita"].tolist()
            x_mean = sum(xs) / len(xs)
            y_mean = sum(ys) / len(ys)
            denom = sum((x - x_mean) ** 2 for x in xs)
            slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom if denom > 0 else 0.0
            intercept = y_mean - slope * x_mean
            next_period = (pd.Period(monthly["mes_ano"].iloc[-1], freq="M") + 1).to_timestamp().strftime("%b/%Y").title()
            trend_x = monthly["mês"].tolist() + [f"{next_period} (Prev.)"]
            trend_y = [max(0.0, intercept + slope * x) for x in range(len(xs) + 1)]
            fig.add_trace(
                go.Scatter(
                    x=trend_x,
                    y=trend_y,
                    mode="lines+markers",
                    name="Tendência / Projeção",
                    line=dict(color="#f59e0b", width=2, dash="dash"),
                )
            )
        fig.update_layout(title="Tendência e projeção de receita mensal", yaxis_title="Receita (R$)")
        st.plotly_chart(plot_layout(fig, 360), width="stretch")

    with right:
        rated = data["avaliacao"].dropna()
        if rated.empty:
            st.info("Não há avaliações registradas no recorte atual.")
        else:
            rating_counts = (
                rated.round().astype(int).value_counts().sort_index()
                .rename_axis("nota")
                .reset_index(name="avaliacoes")
            )
            rating_counts["nota_label"] = rating_counts["nota"].astype(str) + " ★"
            resp_pct = pct(len(rated) / len(data))
            fig = px.bar(
                rating_counts,
                x="nota_label",
                y="avaliacoes",
                text="avaliacoes",
                title=f"Distribuição das avaliações (resposta: {resp_pct})",
                labels={"nota_label": "Nota", "avaliacoes": "Quantidade"},
                color="avaliacoes",
                color_continuous_scale="Tealgrn",
            )
            st.plotly_chart(plot_layout(fig, 360), width="stretch")

    indicator_table = monthly[
        [
            "mês",
            "agendamentos",
            "realizados",
            "taxa_conclusao",
            "taxa_no_show",
            "receita",
            "receita_perdida",
            "descontos",
            "receita_hora",
            "ticket_medio",
            "avaliacao_media",
        ]
    ].rename(
        columns={
            "mês": "Mês",
            "agendamentos": "Agendamentos",
            "realizados": "Realizados",
            "taxa_conclusao": "Taxa de conclusão",
            "taxa_no_show": "Taxa de no-show",
            "receita": "Receita",
            "receita_perdida": "Receita perdida",
            "descontos": "Descontos",
            "receita_hora": "Receita/hora",
            "ticket_medio": "Ticket médio",
            "avaliacao_media": "Avaliação média",
        }
    ).copy()
    indicator_table["Taxa de conclusão"] = indicator_table["Taxa de conclusão"].map(pct)
    indicator_table["Taxa de no-show"] = indicator_table["Taxa de no-show"].map(pct)
    for col in ["Receita", "Receita perdida", "Descontos", "Receita/hora", "Ticket médio"]:
        indicator_table[col] = indicator_table[col].map(brl)
    indicator_table["Avaliação média"] = indicator_table["Avaliação média"].round(2)
    st.dataframe(indicator_table, width="stretch", hide_index=True)


def main() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #07111f; color: #e2e8f0; }
        [data-testid="stSidebar"] { background: #0b1728; }
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
            align-items: stretch;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"],
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="column"] {
            display: flex;
            flex-direction: column;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) [data-testid="stVerticalBlock"],
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) [data-testid="stElementContainer"],
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) .element-container {
            height: 100%;
            display: flex;
            flex-direction: column;
            flex: 1 1 auto;
        }
        [data-testid="stMetric"] {
            background: linear-gradient(135deg, #102b4a, #0c1e35);
            border: 1px solid #1e446b;
            padding: 15px;
            border-radius: 14px;
            height: 100%;
            width: 100%;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        [data-testid="stMetricLabel"] { color: #93c5fd; }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] > div,
        [data-testid="stMetricLabel"] p,
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] > div {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            overflow-wrap: break-word;
            word-break: break-word;
            max-width: 100%;
            line-height: 1.25;
        }
        [data-testid="stMetricValue"] { font-size: clamp(1.05rem, 1.45vw, 1.55rem); }
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

    kpis = compute_kpis(filtered)

    k1, k2, k3, k4, k5, k6 = st.columns([1.0, 1.15, 1.65, 1.25, 1.15, 0.9])
    k1.metric("Agendamentos", format_int(kpis["total"]))
    k2.metric("Serviços realizados", format_int(kpis["completed_count"]))
    k3.metric("Receita concluída", brl(kpis["revenue"]))
    k4.metric("Ticket médio", brl(kpis["ticket"]))
    k5.metric("Taxa de conclusão", pct(kpis["completion_rate"]))
    k6.metric("No-show", format_int(kpis["no_show_count"]))

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Receita prevista (Confirmados)", brl(kpis["predicted_revenue"]))
    s2.metric("Receita perdida (Cancel. + No-show)", brl(kpis["lost_revenue"]))
    s3.metric(
        f"Descontos ({pct(kpis['discount_rate'])})",
        brl(kpis["discounts"]),
    )
    s4.metric("Receita / hora trabalhada", brl(kpis["revenue_per_hour"]))
    st.caption(f"Exibindo {format_int(len(filtered))} de {format_int(len(data))} registros do arquivo após os filtros.")

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
