import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useData,
  useAction,
  ActionError,
  PagedTable,
  Table,
  Metric,
} from "@/components/Data";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Field";
import { AsyncBoundary, InlineNotice } from "@/components/ui/States";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import {
  importStatusLabels,
  importStatusTones,
  rowStatusLabels,
} from "@/lib/labels";
import type {
  Page,
  ImportJob,
  ImportPreview,
  ImportReport,
  ValidationSummary,
  CommitResult,
  RowError,
} from "@/types/api";

export function Imports() {
  const [page, setPage] = useState(1);
  const navigate = useNavigate();
  const { can } = useAuth();
  const q = useData<Page<ImportJob>>("/imports", { page });
  const upload = useAction((form: FormData) =>
    api.upload<ImportJob>("/imports", form),
  );
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const result = await upload
      .mutateAsync(new FormData(e.currentTarget))
      .catch(() => null);
    if (result) navigate(`/imports/${result.id}`);
  }
  return (
    <>
      <PageHeader
        title="Importações"
        description="Transforme planilhas em uma base organizada, com revisão antes de gravar."
      />
      {can("imports:write") && (
        <Card className="mb-6">
          <CardHeader
            title="Nova importação de clientes"
            subtitle="CSV, XLSX ou XLS • cada linha será validada antes da confirmação"
          />
          <CardBody>
            <form
              onSubmit={(e) => void submit(e)}
              className="flex flex-wrap items-end gap-4"
            >
              <Input
                label="Planilha"
                name="file"
                type="file"
                accept=".csv,.xlsx,.xls"
                required
                className="max-w-lg"
              />
              <Button type="submit" loading={upload.isPending}>
                Enviar planilha
              </Button>
            </form>
            <ActionError error={upload.error} />
          </CardBody>
        </Card>
      )}
      <Card>
        <PagedTable
          query={q}
          page={page}
          setPage={setPage}
          columns={[
            {
              title: "Arquivo",
              render: (r) => (
                <Link
                  className="font-medium text-brand-700"
                  to={`/imports/${r.id}`}
                >
                  {r.original_filename}
                </Link>
              ),
            },
            {
              title: "Situação",
              render: (r) => (
                <Badge tone={importStatusTones[r.status]}>
                  {importStatusLabels[r.status]}
                </Badge>
              ),
            },
            { title: "Linhas", render: (r) => r.total_rows },
            { title: "Importadas", render: (r) => r.imported_rows },
            {
              title: "Enviado em",
              render: (r) => formatDateTime(r.created_at),
            },
          ]}
        />
      </Card>
    </>
  );
}

export function ImportDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const [mapping, setMapping] = useState<Record<string, string | null> | null>(
    null,
  );
  const [sheet, setSheet] = useState<string | undefined>();
  const [errorPage, setErrorPage] = useState(1);
  const job = useData<ImportJob>(`/imports/${id}`);
  const preview = useData<ImportPreview>(`/imports/${id}/preview`);
  const report = useData<ImportReport>(`/imports/${id}/report`);
  const errors = useData<Page<RowError>>(
    `/imports/${id}/errors`,
    { page: errorPage },
    job.data?.status === "VALIDATED" || job.data?.status === "COMMITTED",
  );
  const save = useAction(() =>
    api.put<ImportJob>(`/imports/${id}/mapping`, {
      mappings: Object.entries(mapping ?? preview.data?.mapping ?? {}).map(
        ([source_column, target_field]) => ({ source_column, target_field }),
      ),
      sheet_name: sheet ?? preview.data?.active_sheet,
    }),
  );
  const validate = useAction(() =>
    api.post<ValidationSummary>(`/imports/${id}/validate`),
  );
  const commit = useAction(() =>
    api.post<CommitResult>(`/imports/${id}/commit`),
  );
  const completed = job.data?.status === "COMMITTED";
  const busy = save.isPending || validate.isPending || commit.isPending;
  return (
    <>
      <PageHeader
        title={job.data?.original_filename ?? "Revisar importação"}
        description="1. Revise as colunas → 2. Valide as linhas → 3. Confirme a importação"
        actions={
          <Link className="text-brand-700" to="/imports">
            ← Importações
          </Link>
        }
      />
      <AsyncBoundary
        isLoading={job.isLoading || preview.isLoading}
        error={job.error ?? preview.error}
      >
        {job.data && preview.data && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-4">
              <Metric label="Linhas" value={job.data.total_rows} />
              <Metric label="Válidas" value={job.data.valid_rows} />
              <Metric label="Com erro" value={job.data.invalid_rows} />
              <Metric label="Duplicadas" value={job.data.duplicate_rows} />
            </div>
            {completed && (
              <InlineNotice tone="success">
                Importação confirmada. {job.data.imported_rows} clientes criados
                e {job.data.updated_rows} atualizados.
              </InlineNotice>
            )}
            <Card>
              <CardHeader
                title="Mapeamento de colunas"
                subtitle="Confira como cada coluna será interpretada."
              />
              <CardBody>
                {preview.data.available_sheets.length > 1 && (
                  <Select
                    label="Aba da planilha"
                    disabled={completed || !can("imports:write")}
                    value={sheet ?? preview.data.active_sheet ?? ""}
                    options={preview.data.available_sheets.map((s) => ({
                      value: s,
                      label: s,
                    }))}
                    onChange={(e) => setSheet(e.target.value)}
                    className="mb-4"
                  />
                )}
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {preview.data.headers.map((header) => (
                    <Select
                      key={header}
                      label={header}
                      disabled={completed || !can("imports:write")}
                      value={(mapping ?? preview.data?.mapping)?.[header] ?? ""}
                      placeholder="Ignorar coluna"
                      options={preview.data!.canonical_fields.map((f) => ({
                        value: f.field,
                        label: `${f.label}${f.required ? " *" : ""}`,
                      }))}
                      onChange={(e) => {
                        setMapping({
                          ...(mapping ?? preview.data?.mapping),
                          [header]: e.target.value || null,
                        });
                      }}
                    />
                  ))}
                </div>
                {can("imports:write") && !completed && (
                  <div className="mt-6 flex flex-wrap gap-3">
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() =>
                        save.mutate(undefined, {
                          onSuccess: () => setMapping(null),
                        })
                      }
                    >
                      Salvar mapeamento
                    </Button>
                    <Button
                      disabled={
                        busy ||
                        mapping !== null ||
                        (sheet !== undefined &&
                          sheet !== preview.data.active_sheet)
                      }
                      loading={validate.isPending}
                      onClick={() => validate.mutate(undefined)}
                    >
                      Validar linhas
                    </Button>
                    {job.data.status === "VALIDATED" && (
                      <Button
                        disabled={busy || mapping !== null}
                        loading={commit.isPending}
                        onClick={() => commit.mutate(undefined)}
                      >
                        Confirmar importação
                      </Button>
                    )}
                  </div>
                )}
                <ActionError
                  error={save.error ?? validate.error ?? commit.error}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="Prévia dos dados normalizados"
                subtitle="Amostra de até 10 linhas"
              />
              <Table
                rows={preview.data.rows}
                columns={[
                  { title: "Linha", render: (r) => r.row_number },
                  {
                    title: "Cliente",
                    render: (r) =>
                      String(
                        r.normalized.customer_name ??
                          r.raw[preview.data!.headers[0]] ??
                          "—",
                      ),
                  },
                  {
                    title: "E-mail",
                    render: (r) => String(r.normalized.email ?? "—"),
                  },
                  {
                    title: "Situação",
                    render: (r) => rowStatusLabels[r.status],
                  },
                  {
                    title: "Observações",
                    render: (r) =>
                      [...r.errors, ...r.warnings]
                        .map((i) => i.message)
                        .join("; ") || "Sem problemas",
                  },
                ]}
              />
            </Card>
            {report.data?.validation && (
              <Card>
                <CardHeader title="Relatório de validação" />
                <CardBody>
                  <ul className="list-inside list-disc space-y-2 text-sm">
                    {report.data.recommendations.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </CardBody>
                <PagedTable
                  query={errors}
                  page={errorPage}
                  setPage={setErrorPage}
                  columns={[
                    { title: "Linha", render: (r) => r.row_number },
                    {
                      title: "Situação",
                      render: (r) => rowStatusLabels[r.status],
                    },
                    {
                      title: "Motivo",
                      render: (r) =>
                        r.errors
                          .map((e) => `${e.label}: ${e.message}`)
                          .join("; ") ||
                        `Duplicada da linha ${r.duplicate_of_row ?? "existente no banco"}`,
                    },
                  ]}
                />
              </Card>
            )}
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
