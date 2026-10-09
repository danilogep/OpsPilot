import { useState, type FormEvent } from "react";
import {
  useData,
  useAction,
  PagedTable,
  Table,
  ActionError,
} from "@/components/Data";
import { AnswerText } from "@/components/AnswerText";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { AsyncBoundary, InlineNotice } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatDuration } from "@/lib/format";
import {
  agentStatusLabels,
  agentStatusTones,
  documentStatusLabels,
} from "@/lib/labels";
import type {
  Page,
  KnowledgeDocument,
  SearchResponse,
  AssistantAnswer,
  AssistantConfig,
  LlmUsage,
  AgentInfo,
  AgentRunResponse,
} from "@/types/api";

export function Knowledge() {
  const [page, setPage] = useState(1);
  const [term, setTerm] = useState("");
  const [search, setSearch] = useState("");
  const [removeId, setRemoveId] = useState<string | null>(null);
  const { can } = useAuth();
  const docs = useData<Page<KnowledgeDocument>>("/knowledge/documents", {
    page,
  });
  const hits = useData<SearchResponse>(
    "/knowledge/search",
    { q: search },
    search.length >= 2,
  );
  const upload = useAction((form: FormData) =>
    api.upload("/knowledge/documents", form),
  );
  const remove = useAction((id: string) =>
    api.delete(`/knowledge/documents/${id}`),
  );
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    await upload
      .mutateAsync(new FormData(form))
      .then(() => form.reset())
      .catch(() => undefined);
  }
  return (
    <>
      <PageHeader
        title="Base de conhecimento"
        description="Documentos da empresa, pesquisáveis e disponíveis para respostas com fontes."
      />
      {can("knowledge:write") && (
        <Card className="mb-6">
          <CardHeader
            title="Adicionar documento"
            subtitle="TXT, Markdown, PDF com texto, DOCX, CSV ou XLSX"
          />
          <CardBody>
            <form
              onSubmit={(e) => void submit(e)}
              className="grid items-end gap-4 sm:grid-cols-3"
            >
              <Input label="Título (opcional)" name="title" />
              <Input
                label="Documento"
                name="file"
                type="file"
                accept=".txt,.md,.pdf,.docx,.csv,.xlsx"
                required
              />
              <Button type="submit" loading={upload.isPending}>
                Indexar documento
              </Button>
            </form>
            <ActionError error={upload.error} />
            {upload.isSuccess && (
              <p role="status" className="mt-3 text-sm text-success-700">
                Documento indexado.
              </p>
            )}
          </CardBody>
        </Card>
      )}
      <Card className="mb-6">
        <CardHeader title="Pesquisar nos documentos" />
        <CardBody>
          <form
            className="flex items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(term.trim());
            }}
          >
            <Input
              label="Termos de busca"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              minLength={2}
              required
            />
            <Button type="submit">Buscar</Button>
          </form>
          {search && (
            <AsyncBoundary
              isLoading={hits.isLoading}
              error={hits.error}
              isEmpty={!hits.data?.hits.length}
            >
              <div className="mt-5 space-y-4">
                {hits.data?.hits.map((h) => (
                  <article
                    key={h.chunk_id}
                    className="border-l-2 border-brand-500 pl-4"
                  >
                    <strong>{h.document_title}</strong>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-ink-600">
                      {h.excerpt}
                    </p>
                    <p className="mt-1 text-xs text-ink-400">
                      Trecho {h.chunk_index + 1}
                      {h.page_hint ? ` • ${h.page_hint}` : ""}
                    </p>
                  </article>
                ))}
              </div>
            </AsyncBoundary>
          )}
        </CardBody>
      </Card>
      <ActionError error={remove.error} />
      <Card>
        <PagedTable
          query={docs}
          page={page}
          setPage={setPage}
          columns={[
            { title: "Documento", render: (r) => r.title },
            { title: "Trechos", render: (r) => r.chunk_count },
            {
              title: "Situação",
              render: (r) => documentStatusLabels[r.status],
            },
            {
              title: "Incluído em",
              render: (r) => formatDateTime(r.created_at),
            },
            {
              title: "Ações",
              render: (r) =>
                can("knowledge:write") ? (
                  removeId === r.id ? (
                    <div className="flex gap-2">
                      <Button
                        variant="danger"
                        size="sm"
                        loading={remove.isPending}
                        onClick={() =>
                          remove.mutate(r.id, {
                            onSuccess: () => setRemoveId(null),
                          })
                        }
                      >
                        Confirmar exclusão
                      </Button>
                      <Button variant="ghost" onClick={() => setRemoveId(null)}>
                        Cancelar
                      </Button>
                    </div>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setRemoveId(r.id)}
                    >
                      Remover
                    </Button>
                  )
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

function Answer({ answer }: { answer: AssistantAnswer }) {
  return (
    <Card>
      <CardHeader
        title={answer.question}
        actions={
          <Badge tone={answer.has_evidence ? "success" : "warning"}>
            {answer.has_evidence
              ? "Com evidências"
              : "Sem evidências suficientes"}
          </Badge>
        }
      />
      <CardBody>
        <AnswerText text={answer.answer} data-testid="assistant-answer" />
        {answer.facts.length > 0 && (
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {answer.facts.map((f, i) => (
              <div key={i} className="rounded-lg bg-ink-50 p-3">
                <p className="text-xs text-ink-500">{f.label}</p>
                <p className="mt-1 font-semibold">{String(f.value ?? "—")}</p>
              </div>
            ))}
          </div>
        )}
        {answer.recommendation && (
          <div className="mt-5">
            <InlineNotice>{answer.recommendation}</InlineNotice>
          </div>
        )}
        <h3 className="mb-3 mt-6 text-sm font-semibold">Fontes consultadas</h3>
        <div className="space-y-3">
          {answer.sources.length ? (
            answer.sources.map((s, i) => (
              <div key={i} className="rounded-lg border border-ink-200 p-3">
                <p className="text-sm font-medium">
                  {i + 1}. {s.title}
                </p>
                {s.locator && (
                  <p className="text-xs text-ink-500">{s.locator}</p>
                )}
                {s.excerpt && (
                  <blockquote className="mt-2 whitespace-pre-wrap text-sm text-ink-600">
                    {s.excerpt}
                  </blockquote>
                )}
              </div>
            ))
          ) : (
            <p className="text-sm text-ink-500">
              Nenhuma fonte disponível para esta pergunta.
            </p>
          )}
        </div>
        {answer.reasoning.length > 0 && (
          <details className="mt-5 text-sm">
            <summary className="cursor-pointer font-medium">
              Método de cálculo e consulta
            </summary>
            <ul className="mt-2 list-inside list-disc">
              {answer.reasoning.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </details>
        )}
      </CardBody>
    </Card>
  );
}

export function Assistant() {
  const config = useData<AssistantConfig>("/assistant/config");
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<AssistantAnswer[]>([]);
  const ask = useAction((q: string) =>
    api.post<AssistantAnswer>("/assistant/ask", { question: q }),
  );
  const [page, setPage] = useState(1);
  const usage = useData<Page<LlmUsage>>("/assistant/usage", { page });
  function send(q: string) {
    if (q.trim().length < 5 || ask.isPending) return;
    ask.mutate(q, {
      onSuccess: (answer) => {
        setAnswers((previous) => [answer, ...previous]);
        setQuestion("");
      },
    });
  }
  return (
    <>
      <PageHeader
        title="Assistente de IA"
        description="Pergunte sobre a operação e confira os dados usados em cada resposta."
      />
      <AsyncBoundary isLoading={config.isLoading} error={config.error}>
        {config.data && (
          <div className="mb-6">
            <InlineNotice>
              {config.data.is_mock
                ? "Modo demonstração: respostas determinísticas a partir dos dados, sem chamadas a uma IA externa."
                : `Provider ativo: ${config.data.active_provider}. As consultas usam os dados da sua organização.`}
            </InlineNotice>
          </div>
        )}
      </AsyncBoundary>
      <Card className="mb-6">
        <CardBody>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(question);
            }}
            className="space-y-3"
          >
            <Textarea
              label="Sua pergunta"
              placeholder="Quais clientes renovam nos próximos 30 dias?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              minLength={5}
              maxLength={500}
              required
            />
            <Button type="submit" loading={ask.isPending}>
              Consultar dados
            </Button>
          </form>
          <ActionError error={ask.error} />
          <div className="mt-5 flex flex-wrap gap-2">
            {config.data?.suggestions.map((s) => (
              <Button
                key={s}
                variant="secondary"
                size="sm"
                disabled={ask.isPending}
                onClick={() => send(s)}
              >
                {s}
              </Button>
            ))}
          </div>
        </CardBody>
      </Card>
      <div className="space-y-6" aria-live="polite">
        {answers.map((answer, i) => (
          <Answer key={`${answer.generated_at}-${i}`} answer={answer} />
        ))}
      </div>
      <Card className="mt-6">
        <CardHeader
          title="Uso e rastreabilidade"
          subtitle="Execuções registradas no banco, incluindo provider e consumo informado."
        />
        <PagedTable
          query={usage}
          page={page}
          setPage={setPage}
          columns={[
            { title: "Data", render: (r) => formatDateTime(r.created_at) },
            { title: "Recurso", render: (r) => r.feature },
            { title: "Provider", render: (r) => r.provider },
            {
              title: "Tokens",
              render: (r) => r.input_tokens + r.output_tokens,
            },
            { title: "Duração", render: (r) => formatDuration(r.duration_ms) },
            { title: "Situação", render: (r) => r.status },
          ]}
        />
      </Card>
    </>
  );
}

interface AgentHistory {
  id: string;
  agent_name: string;
  status: string;
  tools_used: string[];
  duration_ms: number;
  created_at: string;
}
export function Agents() {
  const catalog = useData<AgentInfo[]>("/agents");
  const [agent, setAgent] = useState("");
  const [question, setQuestion] = useState("");
  const [page, setPage] = useState(1);
  const history = useData<Page<AgentHistory>>("/agents/runs", { page });
  const run = useAction(() =>
    api.post<AgentRunResponse>(
      `/agents/${agent || catalog.data?.[0]?.key}/run`,
      { question },
    ),
  );
  return (
    <>
      <PageHeader
        title="Agentes"
        description="Consultas especializadas com ferramentas limitadas e rastro de execução."
      />
      <Card className="mb-6">
        <CardBody>
          <AsyncBoundary isLoading={catalog.isLoading} error={catalog.error}>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                run.mutate(undefined);
              }}
            >
              <Select
                label="Especialidade"
                value={agent || catalog.data?.[0]?.key || ""}
                options={(catalog.data ?? []).map((a) => ({
                  value: a.key,
                  label: a.name,
                }))}
                onChange={(e) => setAgent(e.target.value)}
              />
              <Textarea
                label="Solicitação"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                minLength={5}
                maxLength={500}
                required
              />
              <Button type="submit" loading={run.isPending}>
                Executar agente
              </Button>
            </form>
          </AsyncBoundary>
          <ActionError error={run.error} />
        </CardBody>
      </Card>
      {run.data && (
        <Card className="mb-6">
          <CardHeader
            title={run.data.agent_name}
            actions={
              <Badge tone={agentStatusTones[run.data.status]}>
                {agentStatusLabels[run.data.status]}
              </Badge>
            }
          />
          <CardBody>
            <AnswerText text={run.data.answer} className="mb-5" />
            <Table
              rows={run.data.steps}
              columns={[
                { title: "Passo", render: (r) => r.index },
                { title: "Ferramenta", render: (r) => r.tool },
                { title: "Objetivo", render: (r) => r.rationale },
                { title: "Situação", render: (r) => r.status },
                {
                  title: "Duração",
                  render: (r) => formatDuration(r.duration_ms),
                },
              ]}
            />
            <p className="mt-4 text-xs text-ink-500">
              Rastreamento: {run.data.correlation_id}
            </p>
          </CardBody>
        </Card>
      )}
      <Card>
        <CardHeader title="Execuções anteriores" />
        <PagedTable
          query={history}
          page={page}
          setPage={setPage}
          columns={[
            { title: "Agente", render: (r) => r.agent_name },
            { title: "Data", render: (r) => formatDateTime(r.created_at) },
            { title: "Ferramentas", render: (r) => r.tools_used.join(", ") },
            { title: "Situação", render: (r) => r.status },
          ]}
        />
      </Card>
    </>
  );
}
