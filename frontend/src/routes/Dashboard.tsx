import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useData, Metric, Table } from "@/components/Data";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Field";
import { AsyncBoundary } from "@/components/ui/States";
import { Badge } from "@/components/ui/Badge";
import {
  formatCurrency,
  formatDate,
  formatMonth,
  formatNumber,
} from "@/lib/format";
import { importStatusLabels, importStatusTones } from "@/lib/labels";
import type { DashboardOverview, CriticalRenewal } from "@/types/api";

export function Dashboard() {
  const [months, setMonths] = useState("6");
  const q = useData<DashboardOverview>("/dashboard/overview", {
    timeline_months: months,
  });
  const critical = useData<CriticalRenewal[]>("/renewals/critical");
  const d = q.data;
  return (
    <>
      <PageHeader
        title="Visão geral"
        description="Os números da sua operação, reunidos em um só lugar."
        actions={
          <Link
            className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white"
            to="/imports"
          >
            + Importar planilha
          </Link>
        }
      />
      <AsyncBoundary
        isLoading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
      >
        {d && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Metric
                label="Receita mensal estimada"
                value={formatCurrency(d.customers.monthly_revenue)}
                hint="Clientes ativos e em atraso"
              />
              <Metric
                label="Clientes cadastrados"
                value={formatNumber(d.customers.total_customers)}
                hint={`${d.customers.active_customers} ativos`}
              />
              <Metric
                label="Oportunidades abertas"
                value={d.leads.open_leads}
                hint={`${d.leads.high_priority_leads} com alta prioridade`}
              />
              <Metric
                label="Renovações em 7 dias"
                value={d.renewals.due_next_7_days}
                hint={`${formatCurrency(d.renewals.amount_at_risk)} em risco`}
              />
            </div>
            <div className="grid gap-6 xl:grid-cols-3">
              <Card className="xl:col-span-2">
                <CardHeader
                  title="Evolução da carteira"
                  subtitle="Novos clientes por mês de início do contrato"
                  actions={
                    <Select
                      aria-label="Período do gráfico"
                      value={months}
                      onChange={(e) => setMonths(e.target.value)}
                      options={[
                        { value: "3", label: "3 meses" },
                        { value: "6", label: "6 meses" },
                        { value: "12", label: "12 meses" },
                      ]}
                    />
                  }
                />
                <CardBody>
                  <div
                    className="h-64"
                    role="img"
                    aria-label="Gráfico de novos clientes por mês"
                  >
                    <ResponsiveContainer>
                      <AreaChart data={d.timeline}>
                        <defs>
                          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="#0d9488"
                              stopOpacity={0.3}
                            />
                            <stop
                              offset="100%"
                              stopColor="#0d9488"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid vertical={false} stroke="#e5e7eb" />
                        <XAxis
                          dataKey="month"
                          tickFormatter={formatMonth}
                          tick={{ fontSize: 11 }}
                        />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                        <Tooltip
                          labelFormatter={(v) => formatMonth(String(v))}
                        />
                        <Area
                          type="monotone"
                          dataKey="new_customers"
                          name="Novos clientes"
                          stroke="#0d9488"
                          fill="url(#area)"
                          strokeWidth={3}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </CardBody>
              </Card>
              <Card>
                <CardHeader
                  title="De onde vêm os leads"
                  subtitle="Volume de oportunidades por origem"
                />
                <CardBody>
                  <div
                    className="h-64"
                    role="img"
                    aria-label="Gráfico de leads por origem"
                  >
                    <ResponsiveContainer>
                      <BarChart data={d.lead_sources} layout="vertical">
                        <XAxis type="number" hide />
                        <YAxis
                          type="category"
                          dataKey="source"
                          width={90}
                          tick={{ fontSize: 11 }}
                        />
                        <Tooltip />
                        <Bar
                          dataKey="total"
                          name="Leads"
                          fill="#0d9488"
                          radius={[0, 4, 4, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardBody>
              </Card>
            </div>
            <div className="grid gap-6 xl:grid-cols-2">
              <Card>
                <CardHeader
                  title="Renovações que pedem atenção"
                  subtitle="Ações prioritárias para manter sua carteira"
                  actions={
                    <Link className="text-sm text-brand-700" to="/renewals">
                      Ver todas →
                    </Link>
                  }
                />
                <AsyncBoundary
                  isLoading={critical.isLoading}
                  error={critical.error}
                  isEmpty={!critical.data?.length}
                >
                  <Table
                    rows={critical.data ?? []}
                    columns={[
                      {
                        title: "Cliente",
                        render: (r) => (
                          <Link
                            className="font-medium text-ink-900"
                            to={`/customers/${r.customer_id}`}
                          >
                            {r.customer_name}
                          </Link>
                        ),
                      },
                      {
                        title: "Vencimento",
                        render: (r) => formatDate(r.due_date),
                      },
                      {
                        title: "Valor",
                        render: (r) => formatCurrency(r.amount),
                      },
                      { title: "Atenção", render: (r) => r.reason },
                    ]}
                  />
                </AsyncBoundary>
              </Card>
              <Card>
                <CardHeader
                  title="Importações recentes"
                  subtitle={`${d.imports.total_imported_rows} linhas importadas • ${d.imports.total_invalid_rows} com erro`}
                />
                <AsyncBoundary
                  isLoading={false}
                  error={null}
                  isEmpty={!d.imports.recent.length}
                >
                  <Table
                    rows={d.imports.recent}
                    columns={[
                      {
                        title: "Arquivo",
                        render: (r) => (
                          <Link
                            className="text-brand-700"
                            to={`/imports/${r.id}`}
                          >
                            {r.filename}
                          </Link>
                        ),
                      },
                      { title: "Linhas", render: (r) => r.total_rows },
                      {
                        title: "Situação",
                        render: (r) => (
                          <Badge tone={importStatusTones[r.status]}>
                            {importStatusLabels[r.status]}
                          </Badge>
                        ),
                      },
                    ]}
                  />
                </AsyncBoundary>
              </Card>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Metric
                label="Renovações em 30 dias"
                value={d.renewals.due_next_30_days}
              />
              <Metric
                label="Chamadas de IA nos últimos 30 dias"
                value={d.ai_usage.calls}
              />
              <Metric
                label="Custo estimado de IA (USD)"
                value={`US$ ${Number(d.ai_usage.estimated_cost_usd).toFixed(4)}`}
                hint="O provider de demonstração não tem cobrança."
              />
            </div>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
