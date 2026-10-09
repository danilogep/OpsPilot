import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { AsyncBoundary, ErrorState } from "@/components/ui/States";
import type { Page } from "@/types/api";

export function useData<T>(
  path: string,
  params?: Record<string, unknown>,
  enabled = true,
) {
  return useQuery({
    queryKey: [path, params],
    queryFn: ({ signal }) => api.get<T>(path, params, signal),
    enabled,
  });
}

export function useAction<T, V>(action: (value: V) => Promise<T>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSuccess: async () => {
      await client.invalidateQueries();
    },
  });
}

export function ActionError({ error }: { error: unknown }) {
  return error ? (
    <ErrorState error={error} title="Não foi possível concluir a ação" />
  ) : null;
}

export function Table<T>({
  rows,
  columns,
}: {
  rows: T[];
  columns: { title: string; render: (row: T) => ReactNode }[];
}) {
  return (
    <div className="table-wrapper">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.title} scope="col">
                {c.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={(row as { id?: string }).id ?? index}>
              {columns.map((c) => (
                <td key={c.title}>{c.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PagedTable<T>({
  query,
  page,
  setPage,
  columns,
}: {
  query: ReturnType<typeof useData<Page<T>>>;
  page: number;
  setPage: (page: number) => void;
  columns: { title: string; render: (row: T) => ReactNode }[];
}) {
  return (
    <AsyncBoundary
      isLoading={query.isLoading}
      error={query.error}
      isEmpty={!query.data?.total}
      onRetry={() => void query.refetch()}
    >
      <Table rows={query.data?.items ?? []} columns={columns} />
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm text-ink-500">
        <span>
          {query.data?.total} registros • página {page} de {query.data?.pages}
        </span>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Anterior
          </Button>
          <Button
            variant="secondary"
            disabled={page >= (query.data?.pages ?? 1)}
            onClick={() => setPage(page + 1)}
          >
            Próxima
          </Button>
        </div>
      </div>
    </AsyncBoundary>
  );
}

export function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <section className="card p-5">
      <p className="text-sm text-ink-500">{label}</p>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-ink-900">
        {value}
      </p>
      {hint && <p className="mt-2 text-xs text-ink-500">{hint}</p>}
    </section>
  );
}

export function options(labels: Record<string, string>) {
  return Object.entries(labels).map(([value, label]) => ({ value, label }));
}
