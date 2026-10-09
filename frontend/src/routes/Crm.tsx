import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useAction,
  useData,
  PagedTable,
  Table,
  ActionError,
  options,
} from "@/components/Data";
import { AnswerText } from "@/components/AnswerText";
import { RecordForm, type FormField } from "@/components/RecordForm";
import { Card, CardHeader, CardBody, PageHeader } from "@/components/ui/Card";
import { Badge, ScoreBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Field";
import { AsyncBoundary, InlineNotice } from "@/components/ui/States";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import {
  customerStatusLabels,
  customerStatusTones,
  leadStatusLabels,
  leadStatusTones,
  renewalStatusLabels,
  renewalStatusTones,
  companySizeLabels,
} from "@/lib/labels";
import type {
  Page,
  Customer,
  CustomerHistoryEntry,
  PlanWithMetrics,
  Lead,
  LeadEvent,
  Renewal,
  LeadClassificationResponse,
  MessageDraftResponse,
  RenewalSummaryResponse,
} from "@/types/api";

const basicFields: FormField[] = [
  { key: "name", label: "Nome", required: true },
  { key: "email", label: "E-mail", type: "email" },
  { key: "phone", label: "Telefone" },
  { key: "source", label: "Origem" },
];
const leadFields: FormField[] = [
  ...basicFields,
  { key: "company", label: "Empresa" },
  { key: "segment", label: "Segmento" },
  { key: "company_size", label: "Porte", options: options(companySizeLabels) },
  { key: "interest", label: "Interesse" },
  {
    key: "status",
    label: "Situação",
    options: options(leadStatusLabels),
    required: true,
  },
  { key: "estimated_value", label: "Valor estimado (R$)", type: "number" },
  { key: "probability", label: "Probabilidade (%)", type: "number" },
  { key: "notes", label: "Observações", type: "textarea" },
];

function CustomerForm({
  customer,
  onDone,
}: {
  customer?: Customer;
  onDone: () => void;
}) {
  const plans = useData<PlanWithMetrics[]>("/plans");
  const fields: FormField[] = [
    ...basicFields,
    { key: "document", label: "CPF/CNPJ" },
    {
      key: "status",
      label: "Situação",
      options: options(customerStatusLabels),
      required: true,
    },
    {
      key: "plan_id",
      label: "Plano",
      options: (plans.data ?? []).map((p) => ({ value: p.id, label: p.name })),
    },
    { key: "monthly_value", label: "Valor mensal (R$)", type: "number" },
    { key: "start_date", label: "Início do contrato", type: "date" },
    { key: "renewal_date", label: "Renovação", type: "date" },
    { key: "notes", label: "Observações", type: "textarea" },
  ];
  return (
    <RecordForm
      fields={fields}
      initial={
        customer
          ? { ...customer, plan_id: customer.plan?.id }
          : { status: "ACTIVE", source: "manual" }
      }
      submit={(data) =>
        customer
          ? api.patch(`/customers/${customer.id}`, data)
          : api.post("/customers", data)
      }
      onDone={onDone}
    />
  );
}

export function Customers() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const { can } = useAuth();
  const filters = { search, status };
  const q = useData<Page<Customer>>("/customers", { ...filters, page });
  const exported = useAction(() =>
    downloadFile("/customers/export", filters, "clientes.csv"),
  );
  return (
    <>
      <PageHeader
        title="Clientes"
        description="A carteira da sua empresa, organizada e atualizada."
        actions={
          <>
            <Button
              variant="secondary"
              loading={exported.isPending}
              onClick={() => exported.mutate(undefined)}
            >
              Exportar CSV
            </Button>
            {can("data:write") && (
              <Button onClick={() => setCreating(!creating)}>
                {creating ? "Fechar cadastro" : "+ Novo cliente"}
              </Button>
            )}
          </>
        }
      />
      <ActionError error={exported.error} />
      {creating && (
        <Card className="mb-6">
          <CardHeader title="Cadastrar cliente" />
          <CardBody>
            <CustomerForm onDone={() => setCreating(false)} />
          </CardBody>
        </Card>
      )}
      <Card>
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Buscar cliente"
              placeholder="Nome, e-mail, documento…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
            <Select
              label="Situação"
              value={status}
              placeholder="Todas"
              options={options(customerStatusLabels)}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </CardBody>
        <PagedTable
          query={q}
          page={page}
          setPage={setPage}
          columns={[
            {
              title: "Cliente",
              render: (r) => (
                <Link
                  className="font-medium text-brand-700"
                  to={`/customers/${r.id}`}
                >
                  {r.name}
                  <span className="block text-xs font-normal text-ink-500">
                    {r.email}
                  </span>
                </Link>
              ),
            },
            { title: "Plano", render: (r) => r.plan?.name ?? "—" },
            {
              title: "Situação",
              render: (r) => (
                <Badge tone={customerStatusTones[r.status]}>
                  {customerStatusLabels[r.status]}
                </Badge>
              ),
            },
            {
              title: "Mensalidade",
              render: (r) => formatCurrency(r.monthly_value),
            },
            { title: "Renovação", render: (r) => formatDate(r.renewal_date) },
          ]}
        />
      </Card>
    </>
  );
}

export function CustomerDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { can } = useAuth();
  const [edit, setEdit] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const q = useData<Customer>(`/customers/${id}`);
  const history = useData<CustomerHistoryEntry[]>(`/customers/${id}/history`);
  const contact = useAction(() => api.post(`/customers/${id}/contact`));
  const remove = useAction(() => api.delete(`/customers/${id}`));
  return (
    <>
      <PageHeader
        title={q.data?.name ?? "Cliente"}
        actions={
          <Link to="/customers" className="text-brand-700">
            ← Clientes
          </Link>
        }
      />
      <AsyncBoundary isLoading={q.isLoading} error={q.error}>
        {q.data && (
          <div className="space-y-6">
            <Card>
              <CardBody>
                {edit ? (
                  <CustomerForm
                    customer={q.data}
                    onDone={() => setEdit(false)}
                  />
                ) : (
                  <>
                    <div className="grid gap-5 sm:grid-cols-3">
                      {[
                        ["E-mail", q.data.email],
                        ["Telefone", q.data.phone_formatted],
                        ["Plano", q.data.plan?.name],
                        ["Mensalidade", formatCurrency(q.data.monthly_value)],
                        ["Renovação", formatDate(q.data.renewal_date)],
                        [
                          "Último contato",
                          formatDateTime(q.data.last_contact_at),
                        ],
                      ].map(([label, value]) => (
                        <div key={label}>
                          <p className="text-xs text-ink-500">{label}</p>
                          <p className="mt-1 font-medium">{value ?? "—"}</p>
                        </div>
                      ))}
                    </div>
                    <p className="mt-5 text-sm">{q.data.notes}</p>
                  </>
                )}
                {can("data:write") && (
                  <div className="mt-6 flex flex-wrap gap-3">
                    <Button variant="secondary" onClick={() => setEdit(!edit)}>
                      {edit ? "Cancelar edição" : "Editar"}
                    </Button>
                    <Button
                      loading={contact.isPending}
                      onClick={() => contact.mutate(undefined)}
                    >
                      Registrar contato
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setConfirmDelete(!confirmDelete)}
                    >
                      Excluir cliente
                    </Button>
                    {confirmDelete && (
                      <Button
                        variant="danger"
                        loading={remove.isPending}
                        onClick={() =>
                          remove.mutate(undefined, {
                            onSuccess: () => navigate("/customers"),
                          })
                        }
                      >
                        Confirmar exclusão
                      </Button>
                    )}
                  </div>
                )}
                {contact.isSuccess && (
                  <p role="status" className="mt-3 text-sm text-success-700">
                    Contato registrado.
                  </p>
                )}
                <ActionError error={contact.error ?? remove.error} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Histórico do cliente" />
              <AsyncBoundary
                isLoading={history.isLoading}
                error={history.error}
                isEmpty={!history.data?.length}
              >
                <Table
                  rows={history.data ?? []}
                  columns={[
                    {
                      title: "Data",
                      render: (r) => formatDateTime(r.created_at),
                    },
                    { title: "Ação", render: (r) => r.summary },
                    { title: "Responsável", render: (r) => r.actor_email },
                  ]}
                />
              </AsyncBoundary>
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}

export function Leads() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const { can } = useAuth();
  const q = useData<Page<Lead>>("/leads", { page, search, status });
  const exported = useAction(() =>
    downloadFile("/leads/export", { search, status }, "leads.csv"),
  );
  return (
    <>
      <PageHeader
        title="Leads"
        description="Priorize oportunidades com critérios transparentes."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => exported.mutate(undefined)}
            >
              Exportar CSV
            </Button>
            {can("data:write") && (
              <Button onClick={() => setCreating(!creating)}>
                {creating ? "Fechar cadastro" : "+ Novo lead"}
              </Button>
            )}
          </>
        }
      />
      <ActionError error={exported.error} />
      {creating && (
        <Card className="mb-6">
          <CardHeader title="Cadastrar oportunidade" />
          <CardBody>
            <RecordForm
              fields={leadFields}
              initial={{
                status: "NEW",
                source: "manual",
                company_size: "UNKNOWN",
              }}
              submit={(data) => api.post("/leads", data)}
              onDone={() => setCreating(false)}
            />
          </CardBody>
        </Card>
      )}
      <Card>
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Buscar lead"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
            <Select
              label="Situação"
              value={status}
              placeholder="Todas"
              options={options(leadStatusLabels)}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </CardBody>
        <PagedTable
          query={q}
          page={page}
          setPage={setPage}
          columns={[
            {
              title: "Oportunidade",
              render: (r) => (
                <Link
                  className="font-medium text-brand-700"
                  to={`/leads/${r.id}`}
                >
                  {r.name}
                  <span className="block text-xs text-ink-500">
                    {r.company}
                  </span>
                </Link>
              ),
            },
            {
              title: "Prioridade",
              render: (r) => <ScoreBadge score={r.score} />,
            },
            {
              title: "Situação",
              render: (r) => (
                <Badge tone={leadStatusTones[r.status]}>
                  {leadStatusLabels[r.status]}
                </Badge>
              ),
            },
            { title: "Origem", render: (r) => r.source },
            {
              title: "Valor estimado",
              render: (r) => formatCurrency(r.estimated_value),
            },
          ]}
        />
      </Card>
    </>
  );
}

export function LeadDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [edit, setEdit] = useState(false);
  const [note, setNote] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const q = useData<Lead>(`/leads/${id}`);
  const events = useData<LeadEvent[]>(`/leads/${id}/events`);
  const classify = useAction(() =>
    api.post<LeadClassificationResponse>(`/assistant/leads/${id}/classify`),
  );
  const draft = useAction(() =>
    api.post<MessageDraftResponse>("/assistant/messages/draft", {
      lead_id: id,
      purpose: "lead",
      detail: "Apresentar a solução e agendar uma conversa",
    }),
  );
  const addNote = useAction(() =>
    api.post(`/leads/${id}/notes`, { note, mark_as_contacted: true }),
  );
  const remove = useAction(() => api.delete(`/leads/${id}`));
  return (
    <>
      <PageHeader
        title={q.data?.name ?? "Lead"}
        description={q.data?.company ?? "Oportunidade comercial"}
        actions={
          <Link className="text-brand-700" to="/leads">
            ← Leads
          </Link>
        }
      />
      <AsyncBoundary isLoading={q.isLoading} error={q.error}>
        {q.data && (
          <div className="space-y-6">
            <Card>
              <CardBody>
                {edit ? (
                  <RecordForm
                    fields={leadFields}
                    initial={{ ...q.data }}
                    submit={(data) => api.patch(`/leads/${id}`, data)}
                    onDone={() => setEdit(false)}
                  />
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-4">
                      <ScoreBadge score={q.data.score} />
                      <Badge tone={leadStatusTones[q.data.status]}>
                        {leadStatusLabels[q.data.status]}
                      </Badge>
                      <strong>{formatCurrency(q.data.estimated_value)}</strong>
                      <span className="text-sm text-ink-500">
                        {q.data.email} •{" "}
                        {q.data.phone_formatted ?? "Telefone não informado"}
                      </span>
                    </div>
                    <p className="mt-4">{q.data.interest}</p>
                    <p className="mt-2 text-sm text-ink-500">
                      {q.data.next_step}
                    </p>
                  </>
                )}
                {can("data:write") && (
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button variant="secondary" onClick={() => setEdit(!edit)}>
                      {edit ? "Cancelar" : "Editar"}
                    </Button>
                    <Button
                      loading={classify.isPending}
                      onClick={() => classify.mutate(undefined)}
                    >
                      Classificar com IA
                    </Button>
                    <Button
                      variant="secondary"
                      loading={draft.isPending}
                      onClick={() => draft.mutate(undefined)}
                    >
                      Sugerir mensagem
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setConfirmDelete(!confirmDelete)}
                    >
                      Excluir
                    </Button>
                    {confirmDelete && (
                      <Button
                        variant="danger"
                        loading={remove.isPending}
                        onClick={() =>
                          remove.mutate(undefined, {
                            onSuccess: () => navigate("/leads"),
                          })
                        }
                      >
                        Confirmar exclusão
                      </Button>
                    )}
                  </div>
                )}
                <ActionError
                  error={classify.error ?? draft.error ?? remove.error}
                />
                {classify.data && (
                  <div className="mt-5 space-y-2 rounded-lg bg-brand-50 p-4">
                    <strong>
                      Classificação: {classify.data.classification.score}/100
                    </strong>
                    <p>{classify.data.classification.summary}</p>
                    <p>{classify.data.classification.next_action}</p>
                    <p className="text-xs">
                      Fontes:{" "}
                      {classify.data.sources.map((s) => s.title).join(", ")}
                    </p>
                  </div>
                )}
                {draft.data && (
                  <div className="mt-5">
                    <InlineNotice>
                      <AnswerText text={draft.data.draft} />
                      <p className="mt-3 text-xs">{draft.data.disclaimer}</p>
                    </InlineNotice>
                  </div>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="Como a prioridade foi calculada"
                subtitle={`Método ${q.data.score_method} • versão ${q.data.score_version}`}
              />
              <Table
                rows={q.data.score_reasons}
                columns={[
                  { title: "Critério", render: (r) => r.label },
                  {
                    title: "Pontos",
                    render: (r) => `${r.points}/${r.max_points}`,
                  },
                  { title: "Justificativa", render: (r) => r.detail },
                ]}
              />
            </Card>
            <Card>
              <CardHeader title="Histórico da oportunidade" />
              <CardBody>
                {can("data:write") && (
                  <form
                    className="mb-5 flex items-end gap-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (note.trim())
                        addNote.mutate(undefined, {
                          onSuccess: () => setNote(""),
                        });
                    }}
                  >
                    <Input
                      label="Registrar contato e observação"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      required
                    />
                    <Button type="submit" loading={addNote.isPending}>
                      Registrar
                    </Button>
                  </form>
                )}
                <ActionError error={addNote.error} />
                <AsyncBoundary
                  isLoading={events.isLoading}
                  error={events.error}
                  isEmpty={!events.data?.length}
                >
                  <Table
                    rows={events.data ?? []}
                    columns={[
                      {
                        title: "Data",
                        render: (r) => formatDateTime(r.created_at),
                      },
                      { title: "Evento", render: (r) => r.description },
                    ]}
                  />
                </AsyncBoundary>
              </CardBody>
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}

export function Renewals() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [days, setDays] = useState("");
  const [creating, setCreating] = useState(false);
  const { can } = useAuth();
  const q = useData<Page<Renewal>>("/renewals", {
    page,
    status,
    within_days: days,
  });
  const customers = useData<Page<Customer>>(
    "/customers",
    { page_size: 200 },
    creating,
  );
  const update = useAction(
    ({ id, status: next }: { id: string; status: string }) =>
      api.patch(`/renewals/${id}`, { status: next }),
  );
  const summary = useAction(() =>
    api.post<RenewalSummaryResponse>("/assistant/renewals/summary"),
  );
  const exported = useAction(() =>
    downloadFile(
      "/renewals/export",
      { status, within_days: days },
      "renovacoes.csv",
    ),
  );
  return (
    <>
      <PageHeader
        title="Renovações"
        description="Acompanhe vencimentos e preserve o relacionamento com seus clientes."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => exported.mutate(undefined)}
            >
              Exportar CSV
            </Button>
            <Button
              loading={summary.isPending}
              onClick={() => summary.mutate(undefined)}
            >
              Resumo executivo
            </Button>
            {can("data:write") && (
              <Button
                variant="secondary"
                onClick={() => setCreating(!creating)}
              >
                Nova renovação
              </Button>
            )}
          </>
        }
      />
      <ActionError error={summary.error ?? update.error ?? exported.error} />
      {summary.data && (
        <Card className="mb-6">
          <CardBody>
            <AnswerText text={summary.data.summary} />
            <ul className="mt-4 list-inside list-disc">
              {summary.data.recommended_actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-ink-500">
              Fontes: {summary.data.sources.map((s) => s.title).join(", ")}
            </p>
          </CardBody>
        </Card>
      )}
      {creating && (
        <Card className="mb-6">
          <CardBody>
            <RecordForm
              fields={[
                {
                  key: "customer_id",
                  label: "Cliente",
                  required: true,
                  options: (customers.data?.items ?? []).map((c) => ({
                    value: c.id,
                    label: c.name,
                  })),
                },
                {
                  key: "due_date",
                  label: "Vencimento",
                  type: "date",
                  required: true,
                },
                {
                  key: "amount",
                  label: "Valor (R$)",
                  type: "number",
                  required: true,
                },
              ]}
              submit={(data) => api.post("/renewals", data)}
              onDone={() => setCreating(false)}
            />
          </CardBody>
        </Card>
      )}
      <Card>
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Situação"
              placeholder="Todas"
              value={status}
              options={options(renewalStatusLabels)}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            />
            <Select
              label="Vencimento"
              placeholder="Todo o período"
              value={days}
              options={[
                { value: "7", label: "Próximos 7 dias" },
                { value: "30", label: "Próximos 30 dias" },
              ]}
              onChange={(e) => {
                setDays(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </CardBody>
        <PagedTable
          query={q}
          page={page}
          setPage={setPage}
          columns={[
            {
              title: "Cliente",
              render: (r) => (
                <Link
                  className="text-brand-700"
                  to={`/customers/${r.customer.id}`}
                >
                  {r.customer.name}
                </Link>
              ),
            },
            { title: "Vencimento", render: (r) => formatDate(r.due_date) },
            { title: "Valor", render: (r) => formatCurrency(r.amount) },
            {
              title: "Situação",
              render: (r) => (
                <Badge tone={renewalStatusTones[r.status]}>
                  {renewalStatusLabels[r.status]}
                </Badge>
              ),
            },
            {
              title: "Atualizar",
              render: (r) =>
                can("data:write") &&
                !["CONFIRMED", "LOST"].includes(r.status) ? (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={update.isPending}
                      onClick={() =>
                        update.mutate({ id: r.id, status: "CONFIRMED" })
                      }
                    >
                      Confirmar
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={update.isPending}
                      onClick={() =>
                        update.mutate({ id: r.id, status: "AT_RISK" })
                      }
                    >
                      Em risco
                    </Button>
                  </div>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Card>
    </>
  );
}

export function Plans() {
  const q = useData<PlanWithMetrics[]>("/plans");
  const { can } = useAuth();
  const [editing, setEditing] = useState<PlanWithMetrics | "new" | null>(null);
  return (
    <>
      <PageHeader
        title="Planos"
        description="Serviços oferecidos e indicadores da carteira."
        actions={
          can("data:write") && (
            <Button onClick={() => setEditing(editing ? null : "new")}>
              {editing ? "Fechar" : "+ Novo plano"}
            </Button>
          )
        }
      />
      {editing && (
        <Card className="mb-6">
          <CardBody>
            <RecordForm
              key={typeof editing === "string" ? editing : editing.id}
              fields={[
                { key: "name", label: "Nome", required: true },
                {
                  key: "monthly_value",
                  label: "Mensalidade (R$)",
                  type: "number",
                  required: true,
                },
                { key: "code", label: "Código" },
                { key: "description", label: "Descrição" },
              ]}
              initial={typeof editing === "string" ? {} : { ...editing }}
              submit={(data) =>
                typeof editing === "string"
                  ? api.post("/plans", data)
                  : api.patch(`/plans/${editing.id}`, data)
              }
              onDone={() => setEditing(null)}
            />
          </CardBody>
        </Card>
      )}
      <Card>
        <AsyncBoundary
          isLoading={q.isLoading}
          error={q.error}
          isEmpty={!q.data?.length}
        >
          <Table
            rows={q.data ?? []}
            columns={[
              { title: "Plano", render: (r) => r.name },
              {
                title: "Mensalidade",
                render: (r) => formatCurrency(r.monthly_value),
              },
              { title: "Clientes", render: (r) => r.customers_count },
              {
                title: "Receita mensal",
                render: (r) => formatCurrency(r.monthly_revenue),
              },
              {
                title: "Ações",
                render: (r) =>
                  can("data:write") ? (
                    <Button variant="ghost" onClick={() => setEditing(r)}>
                      Editar
                    </Button>
                  ) : (
                    "—"
                  ),
              },
            ]}
          />
        </AsyncBoundary>
      </Card>
    </>
  );
}
