# Dashboard JS Barbearia

Dashboard Streamlit para análise de agendamentos, serviços realizados, perfil e frequência dos clientes, desempenho dos profissionais e indicadores operacionais.

## Executar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

O app carrega por padrão `data/JS_Barbearia_Dashboard_Dados.csv`. Também é possível trocar o arquivo pelo carregador da barra lateral.

## Recursos

- filtros por período, status, serviço, categoria, profissional, cliente recorrente, faixa etária, bairro e pagamento;
- visão de agendamentos com status, evolução mensal e mapa de horários;
- serviços concluídos por volume, receita e duração;
- perfil dos clientes, recorrência, bairros e frequência de visitas;
- desempenho dos profissionais com taxa de conclusão, no-show, receita, ticket e avaliação;
- indicadores mensais e download dos dados filtrados.
