import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/Button";
import { AsyncBoundary } from "@/components/ui/States";
import { RecordForm } from "@/components/RecordForm";
import { AuthProvider } from "@/lib/auth";
import { Login } from "@/routes/Login";
import { Customers } from "@/routes/Crm";
import {
  buildQuery,
  request,
  TOKEN_STORAGE_KEY,
  UNAUTHORIZED_EVENT,
} from "@/lib/api";
import { formatDate } from "@/lib/format";

function wrap(component: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuthProvider>{component}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    clear: () => storage.clear(),
    key: (index: number) => [...storage.keys()][index] ?? null,
    get length() {
      return storage.size;
    },
  });
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

describe("interações e estados", () => {
  it("bloqueia duplo clique durante uma ação", async () => {
    const click = vi.fn();
    render(
      <Button loading disabled={false} onClick={click}>
        Salvar
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(click).not.toHaveBeenCalled();
  });
  it("exibe carregamento, erro com retry e estado vazio", async () => {
    const retry = vi.fn();
    const { rerender } = render(
      <AsyncBoundary isLoading error={null}>
        conteúdo
      </AsyncBoundary>,
    );
    expect(screen.getByRole("status")).toBeVisible();
    rerender(
      <AsyncBoundary
        isLoading={false}
        error={new Error("Servidor indisponível")}
        onRetry={retry}
      >
        conteúdo
      </AsyncBoundary>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Tentar novamente" }),
    );
    expect(retry).toHaveBeenCalledOnce();
    rerender(
      <AsyncBoundary isLoading={false} error={null} isEmpty>
        conteúdo
      </AsyncBoundary>,
    );
    expect(screen.getByText("Nenhum registro encontrado")).toBeVisible();
  });
  it("envia formulário com números e campos opcionais normalizados", async () => {
    const submit = vi.fn().mockResolvedValue({});
    wrap(
      <RecordForm
        fields={[
          { key: "name", label: "Nome", required: true },
          { key: "amount", label: "Valor", type: "number" },
          { key: "phone", label: "Telefone" },
        ]}
        submit={submit}
      />,
    );
    await userEvent.type(screen.getByLabelText(/Nome/), "Empresa demonstração");
    await userEvent.type(screen.getByLabelText("Valor"), "123.45");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith({
        name: "Empresa demonstração",
        amount: 123.45,
        phone: null,
      }),
    );
  });
  it("mostra erro de autenticação retornado pela API", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "invalid_credentials",
            message: "Credenciais inválidas.",
          },
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    );
    wrap(<Login />);
    await userEvent.type(screen.getByLabelText("E-mail"), "user@example.com");
    await userEvent.type(screen.getByLabelText("Senha"), "incorreta");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Credenciais inválidas.",
      ),
    );
  });
  it("aplica filtro de situação da listagem na API", async () => {
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            items: [],
            total: 0,
            page: 1,
            page_size: 20,
            pages: 0,
          }),
          { headers: { "Content-Type": "application/json" } },
        ),
    );
    wrap(<Customers />);
    await userEvent.selectOptions(screen.getByLabelText("Situação"), "ACTIVE");
    await waitFor(() =>
      expect(
        vi
          .mocked(fetch)
          .mock.calls.some(([url]) => String(url).includes("status=ACTIVE")),
      ).toBe(true),
    );
  });
});

describe("contrato HTTP e formatação", () => {
  it("codifica arrays e ignora filtros vazios", () =>
    expect(
      buildQuery({
        status: ["ACTIVE", "PAST_DUE"],
        empty: "",
        skip: null,
        page: 2,
      }),
    ).toBe("?status=ACTIVE&status=PAST_DUE&page=2"));
  it("envia o token e interpreta o corpo JSON", async () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "demo-token");
    vi.mocked(fetch).mockResolvedValue(
      new Response('{"ok":true}', {
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(await request("/customers")).toEqual({ ok: true });
    expect(vi.mocked(fetch).mock.calls[0][1]?.headers).toMatchObject({
      Authorization: "Bearer demo-token",
    });
  });
  it("informa expiração da sessão no 401", async () => {
    const expired = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, expired);
    vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 401 }));
    await expect(request("/customers")).rejects.toThrow();
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener(UNAUTHORIZED_EVENT, expired);
  });
  it("traduz falha de rede", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(request("/customers")).rejects.toThrow(
      "Não foi possível falar com a API",
    );
  });
  it("preserva datas sem hora no calendário brasileiro", () =>
    expect(formatDate("2026-10-09")).toBe("09/10/2026"));
});
