import { useState } from "react";
import {
  useData,
  useAction,
  ActionError,
  PagedTable,
  Table,
  options,
} from "@/components/Data";
import { Card, CardHeader, CardBody, PageHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { AsyncBoundary, InlineNotice } from "@/components/ui/States";
import { RecordForm } from "@/components/RecordForm";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  auditActionLabel,
  roleLabels,
  webhookStatusLabels,
  webhookStatusTones,
} from "@/lib/labels";
import type {
  IntegrationStatus,
  WebhookEvent,
  Page,
  AuditEvent,
  AuditActionSummary,
  User,
  Role,
  AssistantConfig,
} from "@/types/api";

export function Integrations() {
  const status = useData<IntegrationStatus>("/integrations/status");
  const [page, setPage] = useState(1);
  const [direction, setDirection] = useState("");
  const { can } = useAuth();
  const events = useData<Page<WebhookEvent>>("/integrations/webhooks/events", {
    page,
    direction,
  });
  const test = useAction(() =>
    api.post<WebhookEvent>("/integrations/webhooks/test", {
      event_type: "demo.test",
      payload: { message: "Teste manual do OpsPilot" },
    }),
  );
  return (
    <>
      <PageHeader
        title="Integrações"
        description="Receba eventos e conecte a operação aos seus fluxos no n8n."
      />
      <AsyncBoundary isLoading={status.isLoading} error={status.error}>
        {status.data && (
          <Card className="mb-6">
            <CardHeader
              title="Conexões e eventos"
              actions={
                <Badge
                  tone={
                    status.data.outbound_url_configured ? "success" : "neutral"
                  }
                >
                  {status.data.outbound_url_configured
                    ? "Saída configurada"
                    : "Saída não configurada"}
                </Badge>
              }
            />
            <CardBody>
              <InlineNotice>
                Configure o destino e o segredo no ambiente do servidor. O
                exemplo de fluxo está em integrations/n8n no repositório.
              </InlineNotice>
              <div className="mt-5 space-y-4">
                {status.data.inbound_endpoints.map((e) => (
                  <div key={e.path}>
                    <strong className="text-sm">{e.description}</strong>
                    <code className="mt-1 block break-all rounded-lg bg-ink-50 p-3 text-xs">
                      {e.method} {e.path}
                    </code>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-ink-500">
                Assinatura: {status.data.signature_header} • Idempotência:{" "}
                {status.data.idempotency_header}
              </p>
              {can("integrations:manage") && (
                <Button
                  className="mt-5"
                  variant="secondary"
                  loading={test.isPending}
                  onClick={() => test.mutate(undefined)}
                >
                  Registrar evento de teste
                </Button>
              )}
              {test.data && (
                <p role="status" className="mt-3 text-sm">
                  Resultado: {webhookStatusLabels[test.data.status]}
                  {test.data.error ? ` — ${test.data.error}` : ""}
                </p>
              )}
              <ActionError error={test.error} />
            </CardBody>
          </Card>
        )}
      </AsyncBoundary>
      <Card>
        <CardHeader
          title="Histórico de eventos"
          actions={
            <Select
              aria-label="Direção"
              placeholder="Todas as direções"
              value={direction}
              options={[
                { value: "INBOUND", label: "Entrada" },
                { value: "OUTBOUND", label: "Saída" },
              ]}
              onChange={(e) => {
                setDirection(e.target.value);
                setPage(1);
              }}
            />
          }
        />
        <PagedTable
          query={events}
          page={page}
          setPage={setPage}
          columns={[
            { title: "Evento", render: (r) => r.event_type },
            {
              title: "Direção",
              render: (r) => (r.direction === "INBOUND" ? "Entrada" : "Saída"),
            },
            {
              title: "Situação",
              render: (r) => (
                <Badge tone={webhookStatusTones[r.status]}>
                  {webhookStatusLabels[r.status]}
                </Badge>
              ),
            },
            { title: "Tentativas", render: (r) => r.attempts },
            { title: "Data", render: (r) => formatDateTime(r.created_at) },
            {
              title: "Detalhes",
              render: (r) => (
                <details>
                  <summary className="cursor-pointer text-brand-700">
                    Ver evento
                  </summary>
                  <pre className="max-w-xs overflow-auto whitespace-pre-wrap text-xs">
                    {JSON.stringify(
                      {
                        payload: r.payload,
                        response: r.response,
                        error: r.error,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              ),
            },
          ]}
        />
      </Card>
    </>
  );
}

export function Audit() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const q = useData<Page<AuditEvent>>("/audit/events", {
    page,
    action,
    actor_email: actor,
  });
  const actions = useData<AuditActionSummary[]>("/audit/actions");
  return (
    <>
      <PageHeader
        title="Auditoria"
        description="Quem fez o quê, quando e em qual registro."
      />
      <Card>
        <CardBody>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Responsável"
              value={actor}
              onChange={(e) => {
                setActor(e.target.value);
                setPage(1);
              }}
            />
            <Select
              label="Ação"
              placeholder="Todas"
              value={action}
              options={(actions.data ?? []).map((a) => ({
                value: a.action,
                label: `${auditActionLabel(a.action)} (${a.total})`,
              }))}
              onChange={(e) => {
                setAction(e.target.value);
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
            { title: "Data", render: (r) => formatDateTime(r.created_at) },
            { title: "Ação", render: (r) => auditActionLabel(r.action) },
            { title: "Descrição", render: (r) => r.summary },
            { title: "Responsável", render: (r) => r.actor_email },
            {
              title: "Rastreamento",
              render: (r) => (
                <details>
                  <summary className="cursor-pointer text-brand-700">
                    Detalhes
                  </summary>
                  <p className="max-w-48 break-all text-xs">
                    {r.correlation_id}
                  </p>
                  <pre className="max-w-xs overflow-auto whitespace-pre-wrap text-xs">
                    {JSON.stringify(r.meta, null, 2)}
                  </pre>
                </details>
              ),
            },
          ]}
        />
      </Card>
    </>
  );
}

export function Settings() {
  const { user, organization, can } = useAuth();
  const users = useData<User[]>("/auth/users", undefined, can("users:manage"));
  const roles = useData<Role[]>("/auth/roles");
  const config = useData<AssistantConfig>("/assistant/config");
  const [creating, setCreating] = useState(false);
  const update = useAction(
    ({ id, ...data }: { id: string; role?: string; is_active?: boolean }) =>
      api.patch(`/auth/users/${id}`, data),
  );
  return (
    <>
      <PageHeader
        title="Configurações"
        description="Perfil de acesso e informações do ambiente."
      />
      <div className="space-y-6">
        <Card>
          <CardHeader title={organization?.name ?? "Organização"} />
          <CardBody>
            <p>
              {user?.full_name} • {user?.email}
            </p>
            <p className="mt-1 text-sm text-ink-500">
              {user && roleLabels[user.role]}
            </p>
            <AsyncBoundary isLoading={config.isLoading} error={config.error}>
              <p className="mt-4 text-sm">
                IA ativa: {config.data?.active_provider} •{" "}
                {config.data?.active_model}
              </p>
            </AsyncBoundary>
            <p className="mt-2 text-sm text-ink-500">
              Provider e credenciais são configurados pelo administrador no
              servidor.
            </p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Papéis e permissões" />
          <AsyncBoundary isLoading={roles.isLoading} error={roles.error}>
            <Table
              rows={roles.data ?? []}
              columns={[
                { title: "Papel", render: (r) => roleLabels[r.key] },
                { title: "Descrição", render: (r) => r.description },
              ]}
            />
          </AsyncBoundary>
        </Card>
        {can("users:manage") && (
          <Card>
            <CardHeader
              title="Usuários da organização"
              actions={
                <Button onClick={() => setCreating(!creating)}>
                  {creating ? "Fechar cadastro" : "+ Novo usuário"}
                </Button>
              }
            />
            <CardBody>
              {creating && (
                <RecordForm
                  fields={[
                    {
                      key: "full_name",
                      label: "Nome completo",
                      required: true,
                    },
                    {
                      key: "email",
                      label: "E-mail",
                      type: "email",
                      required: true,
                    },
                    {
                      key: "password",
                      label: "Senha (mínimo 8 caracteres)",
                      type: "password",
                      required: true,
                    },
                    {
                      key: "role",
                      label: "Papel",
                      required: true,
                      options: options(roleLabels),
                    },
                  ]}
                  initial={{ role: "VIEWER" }}
                  submit={(data) => api.post("/auth/users", data)}
                  onDone={() => setCreating(false)}
                />
              )}
              <ActionError error={update.error} />
            </CardBody>
            <AsyncBoundary isLoading={users.isLoading} error={users.error}>
              <Table
                rows={users.data ?? []}
                columns={[
                  {
                    title: "Usuário",
                    render: (r) => (
                      <span>
                        {r.full_name}
                        <small className="block text-ink-500">{r.email}</small>
                      </span>
                    ),
                  },
                  {
                    title: "Papel",
                    render: (r) => (
                      <Select
                        aria-label={`Papel de ${r.full_name}`}
                        value={r.role}
                        options={options(roleLabels)}
                        disabled={r.id === user?.id || update.isPending}
                        onChange={(e) =>
                          update.mutate({ id: r.id, role: e.target.value })
                        }
                      />
                    ),
                  },
                  {
                    title: "Situação",
                    render: (r) => (
                      <Button
                        variant="ghost"
                        disabled={r.id === user?.id || update.isPending}
                        onClick={() =>
                          update.mutate({ id: r.id, is_active: !r.is_active })
                        }
                      >
                        {r.is_active ? "Desativar" : "Ativar"}
                      </Button>
                    ),
                  },
                ]}
              />
            </AsyncBoundary>
          </Card>
        )}
      </div>
    </>
  );
}
