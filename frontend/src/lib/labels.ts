/** Rótulos em português e cores de estado reutilizados nas telas. */

import type {
  AgentRunStatus,
  CompanySize,
  CustomerStatus,
  DocumentStatus,
  ImportStatus,
  LeadCategory,
  LeadStatus,
  RenewalStatus,
  RowStatus,
  UserRole,
  WebhookStatus,
} from "@/types/api";

export type Tone = "neutral" | "success" | "warning" | "danger" | "brand";

export const customerStatusLabels: Record<CustomerStatus, string> = {
  ACTIVE: "Ativo",
  PAST_DUE: "Atrasado",
  CHURNED: "Cancelado",
  PROSPECT: "Prospect",
};

export const customerStatusTones: Record<CustomerStatus, Tone> = {
  ACTIVE: "success",
  PAST_DUE: "warning",
  CHURNED: "danger",
  PROSPECT: "brand",
};

export const renewalStatusLabels: Record<RenewalStatus, string> = {
  SCHEDULED: "Agendada",
  AT_RISK: "Em risco",
  CONFIRMED: "Confirmada",
  LOST: "Perdida",
};

export const renewalStatusTones: Record<RenewalStatus, Tone> = {
  SCHEDULED: "brand",
  AT_RISK: "warning",
  CONFIRMED: "success",
  LOST: "danger",
};

export const leadStatusLabels: Record<LeadStatus, string> = {
  NEW: "Novo",
  CONTACTED: "Contatado",
  QUALIFIED: "Qualificado",
  PROPOSAL: "Proposta",
  WON: "Ganho",
  LOST: "Perdido",
};

export const leadStatusTones: Record<LeadStatus, Tone> = {
  NEW: "brand",
  CONTACTED: "neutral",
  QUALIFIED: "brand",
  PROPOSAL: "warning",
  WON: "success",
  LOST: "danger",
};

export const leadCategoryLabels: Record<LeadCategory, string> = {
  HOT: "Alta prioridade",
  WARM: "Média prioridade",
  COLD: "Baixa prioridade",
};

export const leadCategoryTones: Record<LeadCategory, Tone> = {
  HOT: "danger",
  WARM: "warning",
  COLD: "neutral",
};

export const companySizeLabels: Record<CompanySize, string> = {
  MEI: "MEI",
  MICRO: "Microempresa",
  SMALL: "Pequena",
  MEDIUM: "Média",
  LARGE: "Grande",
  UNKNOWN: "Não informado",
};

export const importStatusLabels: Record<ImportStatus, string> = {
  UPLOADED: "Enviado",
  MAPPED: "Mapeado",
  VALIDATED: "Validado",
  COMMITTED: "Confirmado",
  FAILED: "Falhou",
};

export const importStatusTones: Record<ImportStatus, Tone> = {
  UPLOADED: "neutral",
  MAPPED: "brand",
  VALIDATED: "warning",
  COMMITTED: "success",
  FAILED: "danger",
};

export const rowStatusLabels: Record<RowStatus, string> = {
  PENDING: "Pendente",
  VALID: "Válida",
  INVALID: "Com erro",
  DUPLICATE: "Duplicada",
  IMPORTED: "Importada",
};

export const rowStatusTones: Record<RowStatus, Tone> = {
  PENDING: "neutral",
  VALID: "success",
  INVALID: "danger",
  DUPLICATE: "warning",
  IMPORTED: "success",
};

export const documentStatusLabels: Record<DocumentStatus, string> = {
  PROCESSING: "Processando",
  READY: "Pronto",
  FAILED: "Falhou",
};

export const webhookStatusLabels: Record<WebhookStatus, string> = {
  RECEIVED: "Recebido",
  PROCESSED: "Processado",
  DUPLICATE: "Duplicado",
  FAILED: "Falhou",
  SENT: "Enviado",
  SKIPPED: "Não enviado",
};

export const webhookStatusTones: Record<WebhookStatus, Tone> = {
  RECEIVED: "neutral",
  PROCESSED: "success",
  DUPLICATE: "warning",
  FAILED: "danger",
  SENT: "success",
  SKIPPED: "neutral",
};

export const agentStatusLabels: Record<AgentRunStatus, string> = {
  RUNNING: "Em execução",
  SUCCESS: "Concluído",
  PARTIAL: "Parcial",
  ERROR: "Erro",
  MAX_STEPS: "Limite de passos",
};

export const agentStatusTones: Record<AgentRunStatus, Tone> = {
  RUNNING: "neutral",
  SUCCESS: "success",
  PARTIAL: "warning",
  ERROR: "danger",
  MAX_STEPS: "warning",
};

export const roleLabels: Record<UserRole, string> = {
  ADMIN: "Administrador",
  ANALYST: "Analista",
  VIEWER: "Visualizador",
};

/** Ações de auditoria em linguagem de negócio. */
export const auditActionLabels: Record<string, string> = {
  "auth.login": "Login realizado",
  "auth.login_failed": "Tentativa de login",
  "user.created": "Usuário criado",
  "user.updated": "Usuário atualizado",
  "import.upload": "Arquivo enviado",
  "import.mapping_updated": "Mapeamento revisado",
  "import.validated": "Importação validada",
  "import.committed": "Importação confirmada",
  "customer.created": "Cliente criado",
  "customer.updated": "Cliente atualizado",
  "customer.deleted": "Cliente excluído",
  "customer.contacted": "Contato registrado",
  "plan.created": "Plano criado",
  "plan.updated": "Plano atualizado",
  "plan.deleted": "Plano excluído",
  "lead.created": "Lead criado",
  "lead.updated": "Lead atualizado",
  "lead.scored": "Score recalculado",
  "lead.note_added": "Nota no lead",
  "lead.deleted": "Lead excluído",
  "renewal.created": "Renovação criada",
  "renewal.updated": "Renovação atualizada",
  "knowledge.uploaded": "Documento indexado",
  "knowledge.deleted": "Documento removido",
  "ai.assistant_query": "Pergunta ao assistente",
  "ai.agent_run": "Execução de agente",
  "ai.lead_classified": "Lead classificado por IA",
  "ai.renewal_summary": "Resumo de renovações",
  "ai.message_drafted": "Mensagem sugerida",
  "webhook.received": "Webhook recebido",
  "webhook.sent": "Webhook enviado",
  "seed.completed": "Dados de demonstração",
};

export function auditActionLabel(action: string): string {
  return auditActionLabels[action] ?? action;
}

/** Rótulos dos campos canônicos da importação. */
export const canonicalFieldLabels: Record<string, string> = {
  customer_name: "Nome do cliente",
  email: "E-mail",
  phone: "Telefone",
  document: "CPF/CNPJ",
  plan_name: "Plano",
  customer_status: "Situação",
  start_date: "Início do contrato",
  renewal_date: "Data de renovação",
  monthly_value: "Valor mensal",
  source: "Origem",
  notes: "Observações",
};

export function canonicalFieldLabel(field: string | null): string {
  if (!field) return "Não mapeado";
  return canonicalFieldLabels[field] ?? field;
}
