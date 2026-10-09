/**
 * Cliente HTTP do OpsPilot.
 *
 * - injeta o token JWT guardado pela sessão;
 * - traduz o envelope de erro da API (`{error: {code, message}}`) em `ApiError`
 *   com mensagem em português pronta para a interface;
 * - em 401 dispara um evento global para que a aplicação volte ao login.
 */

import type { ApiErrorBody } from "@/types/api";

export const API_BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000"
).replace(/\/$/, "");

export const API_PREFIX = "/api/v1";
export const TOKEN_STORAGE_KEY = "opspilot.token";
export const UNAUTHORIZED_EVENT = "opspilot:unauthorized";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly correlationId?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
  }

  /** Mensagens de campo vindas de erros de validação da API. */
  get fieldErrors(): { field: string; message: string }[] {
    const fields = this.details.fields;
    if (!Array.isArray(fields)) return [];
    return fields as { field: string; message: string }[];
  }
}

export function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* modo privado sem storage: a sessão vive apenas em memória */
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, unknown>;
  formData?: FormData;
  signal?: AbortSignal;
  /** Quando `true`, não envia o cabeçalho Authorization. */
  anonymous?: boolean;
}

export function buildQuery(query: Record<string, unknown> | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== null && item !== "")
          params.append(key, String(item));
      }
      continue;
    }
    params.append(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

function notifyUnauthorized(): void {
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Falha na requisição (HTTP ${response.status}).`;
  let details: Record<string, unknown> = {};
  let correlationId: string | undefined;

  try {
    const payload = (await response.json()) as Partial<ApiErrorBody>;
    if (payload.error) {
      code = payload.error.code ?? code;
      message = payload.error.message ?? message;
      details = payload.error.details ?? {};
      correlationId = payload.error.correlation_id;
    }
  } catch {
    /* resposta sem corpo JSON: mantém a mensagem padrão */
  }

  if (response.status === 0) {
    message =
      "Não foi possível falar com a API. Verifique se o backend está no ar.";
  }
  return new ApiError(response.status, code, message, details, correlationId);
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, formData, signal, anonymous } = options;
  const headers: Record<string, string> = { Accept: "application/json" };

  if (!anonymous) {
    const token = readToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  if (body !== undefined && !formData)
    headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}${API_PREFIX}${path}${buildQuery(query)}`,
      {
        method,
        headers,
        body:
          formData ?? (body === undefined ? undefined : JSON.stringify(body)),
        signal,
      },
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      "network_error",
      "Não foi possível falar com a API. Verifique se o backend está no ar.",
    );
  }

  if (response.status === 401) {
    notifyUnauthorized();
    throw await toApiError(response);
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json"))
    return (await response.json()) as T;
  return (await response.text()) as unknown as T;
}

/** Faz download de um arquivo gerado pela API (CSV de exportação). */
export async function downloadFile(
  path: string,
  query: Record<string, unknown> | undefined,
  filename: string,
): Promise<void> {
  const token = readToken();
  const response = await fetch(
    `${API_BASE_URL}${API_PREFIX}${path}${buildQuery(query)}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    },
  );
  if (!response.ok) throw await toApiError(response);

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export const api = {
  get: <T>(
    path: string,
    query?: Record<string, unknown>,
    signal?: AbortSignal,
  ) => request<T>(path, { method: "GET", query, signal }),
  post: <T>(path: string, body?: unknown, query?: Record<string, unknown>) =>
    request<T>(path, { method: "POST", body, query }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", formData }),
};

/** Health check do backend (fora do prefixo /api/v1). */
export async function fetchHealth(): Promise<{
  status: string;
  version: string;
  environment: string;
  database: string;
  llm_provider: string;
}> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as {
    status: string;
    version: string;
    environment: string;
    database: string;
    llm_provider: string;
  };
}
