import { test, expect, type Page } from "@playwright/test";

async function login(page: Page, role = "admin") {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(`${role}@opspilot.local`);
  await page
    .getByLabel("Senha")
    .fill(process.env.E2E_PASSWORD ?? "OpsPilot!2026");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Visão geral", exact: true }),
  ).toBeVisible();
}
test("importação completa → painel → resposta fundamentada", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("link", { name: "Importações", exact: true }).click();
  const stamp = Date.now();
  const csv = `cliente,email,plano,valor,renovacao\nEmpresa E2E ${stamp},e2e${stamp}@example.com,Plano E2E,150.00,2027-01-15\nCliente inválido,invalid-email,Plano E2E,150.00,data-incorreta\n`;
  await page.locator('input[type="file"]').setInputFiles({
      name: `teste-${stamp}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
  });
  await page.getByRole("button", { name: "Enviar planilha" }).click();
  await expect(
    page.getByRole("heading", { name: "Mapeamento de colunas" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Salvar mapeamento" }).click();
  await page.getByRole("button", { name: "Validar linhas" }).click();
  await expect(
    page.getByRole("heading", { name: "Relatório de validação" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(
    page.getByText(/Importação confirmada\. 1 clientes/),
  ).toBeVisible();
  await page.getByRole("link", { name: "Clientes", exact: true }).click();
  await page.getByLabel("Buscar cliente").fill(`Empresa E2E ${stamp}`);
  await expect(
    page.getByRole("link", { name: new RegExp(`Empresa E2E ${stamp}`) }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Visão geral", exact: true }).click();
  await expect(
    page.getByText("Receita mensal estimada", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Assistente de IA", exact: true })
    .click();
  await page
    .getByLabel("Sua pergunta")
    .fill("Quantos clientes temos cadastrados?");
  await page.getByRole("button", { name: "Consultar dados" }).click();
  await expect(page.getByTestId("assistant-answer")).toBeVisible();
  await expect(
    page.getByText("Fontes consultadas", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("cadastro de lead, classificação, mensagem e histórico", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Leads", exact: true }).click();
  await page.getByRole("button", { name: "+ Novo lead" }).click();
  const name = `Lead E2E ${Date.now()}`;
  await page.getByLabel("Nome", { exact: false }).fill(name);
  await page.getByLabel("E-mail", { exact: true }).fill("demo@example.com");
  await page
    .getByLabel("Interesse", { exact: true })
    .fill("Automação de processos");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await page.getByLabel("Buscar lead").fill(name);
  await page.getByRole("link", { name, exact: true }).click();
  await page.getByRole("button", { name: "Classificar com IA" }).click();
  await expect(page.getByText(/Classificação:/)).toBeVisible();
  await page.getByRole("button", { name: "Sugerir mensagem" }).click();
  await expect(page.getByText(/o OpsPilot não envia mensagens/)).toBeVisible();
  await page
    .getByLabel("Registrar contato e observação")
    .fill("Contato E2E registrado");
  await page.getByRole("button", { name: "Registrar", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "Contato E2E registrado", exact: true }),
  ).toBeVisible();
});
test("conhecimento, agente, integrações e navegação sem erros", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("link", { name: "Conhecimento", exact: true }).click();
  await page.getByLabel("Título (opcional)").fill("Garantia de demonstração");
  await page.locator('input[type="file"]').setInputFiles({
      name: "garantia.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "A política de garantia da empresa fictícia Zafira cobre substituição de produtos durante doze meses após a compra.",
      ),
  });
  await page.getByRole("button", { name: "Indexar documento" }).click();
  await expect(
    page.getByText("Documento indexado.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Termos de busca").fill("garantia Zafira");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(
    page.getByText(/política de garantia da empresa fictícia Zafira/).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "Agentes", exact: true }).click();
  await page.getByLabel("Solicitação").fill("Quantos clientes temos?");
  await page.getByRole("button", { name: "Executar agente" }).click();
  await expect(page.getByText(/Rastreamento:/)).toBeVisible();
  await page.getByRole("link", { name: "Integrações", exact: true }).click();
  await page.getByRole("button", { name: "Registrar evento de teste" }).click();
  await expect(page.getByText(/Resultado:/)).toBeVisible();
  for (const title of ["Renovações", "Planos", "Auditoria", "Configurações"]) {
    await page.getByRole("link", { name: title, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("error-state")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});
test("visualizador não tem controles de escrita e recebe 403 na API", async ({
  page,
  request,
}) => {
  await login(page, "viewer");
  await page.getByRole("link", { name: "Clientes", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "+ Novo cliente" }),
  ).toHaveCount(0);
  const token = await page.evaluate(() =>
    localStorage.getItem("opspilot.token"),
  );
  const response = await request.post(
    `${process.env.E2E_API_URL ?? "http://localhost:8000"}/api/v1/customers`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { name: "Não deve criar" },
    },
  );
  expect(response.status()).toBe(403);
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Entrar", exact: true }),
  ).toBeVisible();
  await page.goto("/customers");
  await expect(
    page.getByRole("button", { name: "Entrar", exact: true }),
  ).toBeVisible();
});
test("navegação mobile e captura do dashboard", async ({ page }) => {
  await login(page);
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir navegação" }).click();
  await page.getByRole("link", { name: "Importações", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Importações", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/imports-mobile.png",
    fullPage: true,
  });
});
