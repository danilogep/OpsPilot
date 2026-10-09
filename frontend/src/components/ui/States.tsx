import clsx from "clsx";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";

export function Spinner({ className }: { className?: string }): JSX.Element {
  return (
    <span
      role="status"
      aria-label="Carregando"
      className={clsx(
        "inline-block h-5 w-5 animate-spin rounded-full border-2 border-brand-600 border-t-transparent",
        className,
      )}
    />
  );
}

export function LoadingState({
  label = "Carregando dados…",
}: {
  label?: string;
}): JSX.Element {
  return (
    <div
      data-testid="loading-state"
      className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-sm text-ink-500"
    >
      <Spinner />
      <p>{label}</p>
    </div>
  );
}

export function TableSkeleton({
  rows = 5,
  columns = 5,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <div data-testid="table-skeleton" className="space-y-2 px-5 py-4">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <div
              key={columnIndex}
              className="skeleton h-4 flex-1"
              style={{ opacity: 1 - rowIndex * 0.12 }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: EmptyStateProps): JSX.Element {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center"
    >
      <div className="mb-1 flex h-11 w-11 items-center justify-center rounded-full bg-ink-100 text-ink-500">
        {icon ?? <span aria-hidden="true">∅</span>}
      </div>
      <h3 className="text-sm font-semibold text-ink-800">{title}</h3>
      {description ? (
        <p className="max-w-md text-sm text-ink-500">{description}</p>
      ) : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

export interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Erro inesperado ao carregar os dados.";
}

export function ErrorState({
  error,
  onRetry,
  title,
}: ErrorStateProps): JSX.Element {
  const apiError = error instanceof ApiError ? error : null;
  return (
    <div
      role="alert"
      data-testid="error-state"
      className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center"
    >
      <div className="mb-1 flex h-11 w-11 items-center justify-center rounded-full bg-danger-50 text-danger-700">
        <span aria-hidden="true">!</span>
      </div>
      <h3 className="text-sm font-semibold text-ink-900">
        {title ?? "Não foi possível carregar"}
      </h3>
      <p className="max-w-md text-sm text-ink-600">{errorMessage(error)}</p>
      {apiError?.correlationId ? (
        <p className="font-mono text-xs text-ink-400">
          id: {apiError.correlationId}
        </p>
      ) : null}
      {onRetry ? (
        <Button
          variant="secondary"
          size="sm"
          className="mt-3"
          onClick={onRetry}
        >
          Tentar novamente
        </Button>
      ) : null}
    </div>
  );
}

export interface AsyncBoundaryProps {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  onRetry?: () => void;
  loadingFallback?: ReactNode;
  emptyFallback?: ReactNode;
  children: ReactNode;
}

/** Padroniza carregamento, erro e vazio em todas as telas. */
export function AsyncBoundary({
  isLoading,
  error,
  isEmpty = false,
  onRetry,
  loadingFallback,
  emptyFallback,
  children,
}: AsyncBoundaryProps): JSX.Element {
  if (isLoading) return <>{loadingFallback ?? <LoadingState />}</>;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (isEmpty) {
    return (
      <>{emptyFallback ?? <EmptyState title="Nenhum registro encontrado" />}</>
    );
  }
  return <>{children}</>;
}

export function InlineNotice({
  tone = "info",
  children,
}: {
  tone?: "info" | "warning" | "danger" | "success";
  children: ReactNode;
}): JSX.Element {
  const tones = {
    info: "border-brand-200 bg-brand-50 text-brand-900",
    warning: "border-warning-100 bg-warning-50 text-warning-700",
    danger: "border-danger-100 bg-danger-50 text-danger-700",
    success: "border-success-100 bg-success-50 text-success-700",
  } as const;
  return (
    <div className={clsx("rounded-lg border px-4 py-3 text-sm", tones[tone])}>
      {children}
    </div>
  );
}
