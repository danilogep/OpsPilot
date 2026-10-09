/** Formatação em português do Brasil. */

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const compactCurrencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});

const numberFormatter = new Intl.NumberFormat("pt-BR");

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "2-digit",
});

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatCurrency(
  value: string | number | null | undefined,
): string {
  return currencyFormatter.format(toNumber(value));
}

export function formatCompactCurrency(
  value: string | number | null | undefined,
): string {
  return compactCurrencyFormatter.format(toNumber(value));
}

export function formatNumber(
  value: string | number | null | undefined,
): string {
  return numberFormatter.format(toNumber(value));
}

export function formatPercent(
  value: number | null | undefined,
  decimals = 1,
): string {
  const number = (value ?? 0) * 100;
  return `${number.toFixed(decimals).replace(".", ",")}%`;
}

/** Datas ISO sem hora (``2026-10-09``) não devem sofrer ajuste de fuso. */
function parseDate(value: string): Date | null {
  if (!value) return null;
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = isDateOnly ? new Date(`${value}T12:00:00`) : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = parseDate(value);
  return date ? dateFormatter.format(date) : "—";
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = parseDate(value);
  return date ? dateTimeFormatter.format(date) : "—";
}

export function formatMonth(value: string): string {
  const date = parseDate(`${value}-01`);
  return date ? monthFormatter.format(date).replace(".", "") : value;
}

export function formatRelativeDays(days: number | null | undefined): string {
  if (days === null || days === undefined) return "—";
  if (days === 0) return "hoje";
  if (days === 1) return "amanhã";
  if (days === -1) return "ontem";
  if (days > 0) return `em ${formatNumber(days)} dias`;
  return `há ${formatNumber(Math.abs(days))} dias`;
}

export function formatDuration(
  milliseconds: number | null | undefined,
): string {
  const value = milliseconds ?? 0;
  if (value < 1000) return `${formatNumber(value)} ms`;
  return `${(value / 1000).toFixed(1).replace(".", ",")} s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  const value = bytes ?? 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024)
    return `${(value / 1024).toFixed(1).replace(".", ",")} KB`;
  return `${(value / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

export function truncate(value: string, size = 120): string {
  return value.length > size ? `${value.slice(0, size)}…` : value;
}

/** Renderiza negrito simples (``**texto**``) e listas do texto gerado pela IA. */
export function splitAnswerLines(answer: string): string[] {
  return answer.split("\n").filter((line) => line.trim().length > 0);
}
