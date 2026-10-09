/**
 * Gera as capturas de tela usadas no README, a partir do ambiente em execução.
 *
 * Uso (com `docker compose up -d` no ar e o seed de demonstração aplicado):
 *
 *   cd frontend
 *   node scripts/capture-screenshots.mjs
 *
 * As imagens vão para `docs/img/`. O script percorre o fluxo real da aplicação
 * — importa a planilha sintética, valida, confirma e consulta o assistente —
 * então as telas mostram dados verdadeiros do banco, não maquetes.
 */

import { fileURLToPath } from "node:url";
import path from "node:path";

import { chromium } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const PASSWORD = process.env.E2E_PASSWORD ?? "OpsPilot!2026";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const outputDir = path.join(repoRoot, "docs", "img");
const sampleCsv = path.join(repoRoot, "data", "samples", "customers.csv");

/** Espera o React assentar antes de fotografar. */
async function settle(page, milliseconds = 700) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(milliseconds);
}

async function shot(page, name, options = {}) {
  const file = path.join(outputDir, `${name}.png`);
  await settle(page);
  await page.screenshot({ path: file, ...options });
  console.log(`  capturado  docs/img/${name}.png`);
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1040 },
    deviceScaleFactor: 2,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);

  console.log("login…");
  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel("E-mail").fill("admin@opspilot.local");
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("heading", { name: "Visão geral", exact: true }).waitFor();

  console.log("importação da planilha sintética…");
  await page.getByRole("link", { name: "Importações", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(sampleCsv);
  await page.getByRole("button", { name: "Enviar planilha" }).click();
  await page.getByRole("heading", { name: "Mapeamento de colunas" }).waitFor();
  await shot(page, "importacao-mapeamento");

  await page.getByRole("button", { name: "Salvar mapeamento" }).click();
  await page.getByRole("button", { name: "Validar linhas" }).click();
  await page.getByRole("heading", { name: "Relatório de validação" }).waitFor();
  await shot(page, "importacao-validacao");

  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await page.getByText(/Importação confirmada/).waitFor();

  console.log("painel…");
  await page.getByRole("link", { name: "Visão geral", exact: true }).click();
  await page.getByText("Receita mensal estimada", { exact: true }).waitFor();
  const period = page.locator("select").first();
  if (await period.count()) {
    await period.selectOption({ label: "12 meses" }).catch(() => {});
  }
  await shot(page, "dashboard");

  console.log("assistente…");
  await page.getByRole("link", { name: "Assistente de IA", exact: true }).click();
  await page.getByLabel("Sua pergunta").fill("Qual é o valor mensal em risco?");
  await page.getByRole("button", { name: "Consultar dados" }).click();
  await page.getByTestId("assistant-answer").waitFor();
  await shot(page, "assistente");

  console.log("mobile…");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "Visão geral", exact: true }).click().catch(async () => {
    await page.getByRole("button", { name: "Abrir navegação" }).click();
    await page.getByRole("link", { name: "Visão geral", exact: true }).click();
  });
  await page.getByText("Receita mensal estimada", { exact: true }).waitFor();
  await shot(page, "mobile", { fullPage: false });

  await browser.close();
  console.log(`\nimagens em ${path.relative(repoRoot, outputDir)}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
