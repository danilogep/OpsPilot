/**
 * Tipos espelhando os schemas da API do OpsPilot.
 *
 * Mantidos à mão (sem geração automática) para que o build do frontend não
 * dependa de o backend estar rodando. Qualquer mudança de contrato aparece como
 * erro de tipo na tela que a consome.
 */

export type UserRole = "ADMIN" | "ANALYST" | "VIEWER";

export type CustomerStatus = "ACTIVE" | "PAST_DUE" | "CHURNED" | "PROSPECT";

export type RenewalStatus = "SCHEDULED" | "AT_RISK" | "CONFIRMED" | "LOST";

export type LeadStatus =
  | "NEW"
  | "CONTACTED"
  | "QUALIFIED"
  | "PROPOSAL"
  | "WON"
  | "LOST";

export type LeadCategory = "HOT" | "WARM" | "COLD";

export type CompanySize =
  | "MEI"
  | "MICRO"
  | "SMALL"
  | "MEDIUM"
  | "LARGE"
  | "UNKNOWN";

export type ImportStatus =
  | "UPLOADED"
  | "MAPPED"
  | "VALIDATED"
  | "COMMITTED"
  | "FAILED";

export type RowStatus =
  | "PENDING"
  | "VALID"
  | "INVALID"
  | "DUPLICATE"
  | "IMPORTED";

export type DocumentStatus = "PROCESSING" | "READY" | "FAILED";

export type WebhookDirection = "INBOUND" | "OUTBOUND";

export type WebhookStatus =
  | "RECEIVED"
  | "PROCESSED"
  | "DUPLICATE"
  | "FAILED"
  | "SENT"
  | "SKIPPED";

export type AgentRunStatus =
  | "RUNNING"
  | "SUCCESS"
  | "PARTIAL"
  | "ERROR"
  | "MAX_STEPS";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    correlation_id?: string;
  };
}

/* ----------------------------------------------------------- autenticação -- */

export interface User {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  organization: OrganizationSummary;
}

export interface Role {
  key: UserRole;
  name: string;
  description: string;
  permissions: string[];
}

/* -------------------------------------------------------------- dashboard -- */

export interface CustomerOverview {
  total_customers: number;
  active_customers: number;
  past_due_customers: number;
  churned_customers: number;
  prospect_customers: number;
  monthly_revenue: string;
  average_ticket: string;
  by_status: Record<string, { total: number; monthly_value: string }>;
}

export interface RenewalOverview {
  reference_date: string;
  due_next_7_days: number;
  amount_next_7_days: string;
  due_next_30_days: number;
  amount_next_30_days: string;
  overdue: number;
  amount_overdue: string;
  at_risk: number;
  amount_at_risk: string;
  customers_without_recent_contact: number;
  contact_threshold_days: number;
}

export interface LeadOverview {
  total_leads: number;
  open_leads: number;
  high_priority_leads: number;
  estimated_pipeline: string;
  average_score: number;
  won_leads: number;
}

export interface PlanRankingItem {
  plan_name: string;
  customers: number;
  monthly_revenue: string;
  churned_customers: number;
  churn_rate: number;
}

export interface LeadSourceItem {
  source: string;
  total: number;
  average_score: number;
  estimated_value: string;
  won: number;
}

export interface ImportSummaryItem {
  id: string;
  filename: string;
  status: ImportStatus;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  imported_rows: number;
  created_at: string;
}

export interface ImportOverview {
  total_imports: number;
  total_invalid_rows: number;
  total_duplicate_rows: number;
  total_imported_rows: number;
  pending_commit: number;
  recent: ImportSummaryItem[];
}

export interface AiUsageOverview {
  window_days: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  average_duration_ms: number;
  by_feature: { feature: string; calls: number }[];
}

export interface TimelinePoint {
  month: string;
  new_customers: number;
  added_monthly_value: string;
  churned_customers: number;
}

export interface DashboardOverview {
  generated_at: string;
  reference_date: string;
  customers: CustomerOverview;
  renewals: RenewalOverview;
  leads: LeadOverview;
  plans: PlanRankingItem[];
  lead_sources: LeadSourceItem[];
  imports: ImportOverview;
  ai_usage: AiUsageOverview;
  timeline: TimelinePoint[];
}

/* --------------------------------------------------------------- clientes -- */

export interface PlanSummary {
  id: string;
  name: string;
  monthly_value: string;
}

export interface Plan extends PlanSummary {
  code: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PlanWithMetrics extends Plan {
  customers_count: number;
  active_customers: number;
  churned_customers: number;
  monthly_revenue: string;
  churn_rate: number;
}

export interface Customer {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  phone_formatted: string | null;
  document: string | null;
  status: CustomerStatus;
  plan: PlanSummary | null;
  monthly_value: string;
  start_date: string | null;
  renewal_date: string | null;
  days_to_renewal: number | null;
  source: string | null;
  notes: string | null;
  last_contact_at: string | null;
  days_since_contact: number | null;
  import_job_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerHistoryEntry {
  id: string;
  action: string;
  summary: string;
  actor_email: string;
  meta: Record<string, unknown>;
  created_at: string;
}

/* ------------------------------------------------------------- renovações -- */

export interface Renewal {
  id: string;
  customer: {
    id: string;
    name: string;
    email: string | null;
    phone: string | null;
    status: CustomerStatus;
  };
  plan_id: string | null;
  plan_name: string | null;
  due_date: string;
  days_until_due: number | null;
  amount: string;
  status: RenewalStatus;
  confirmed_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface RenewalIndicators {
  due_next_7_days: number;
  due_next_30_days: number;
  overdue: number;
  amount_at_risk: string;
  amount_next_30_days: string;
  customers_without_recent_contact: number;
  contact_threshold_days: number;
  confirmed_last_30_days: number;
  lost_last_30_days: number;
  reference_date: string;
}

export interface CriticalRenewal {
  customer_id: string;
  customer_name: string;
  plan_name: string | null;
  due_date: string;
  days_until_due: number;
  amount: string;
  status: RenewalStatus;
  customer_status: CustomerStatus;
  reason: string;
}

/* ------------------------------------------------------------------ leads -- */

export interface ScoreReason {
  criterion: string;
  label: string;
  points: number;
  max_points: number;
  detail: string;
}

export interface Lead {
  id: string;
  name: string;
  company: string | null;
  email: string | null;
  phone: string | null;
  phone_formatted: string | null;
  source: string;
  segment: string | null;
  company_size: CompanySize;
  interest: string | null;
  status: LeadStatus;
  estimated_value: string;
  probability: number;
  score: number;
  score_category: LeadCategory;
  score_reasons: ScoreReason[];
  score_method: "RULES" | "LLM";
  score_version: string;
  scored_at: string | null;
  next_step: string | null;
  risks: string[];
  suggested_message: string | null;
  last_interaction_at: string | null;
  days_since_interaction: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadEvent {
  id: string;
  event_type: string;
  description: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface LeadIndicators {
  total: number;
  open_leads: number;
  high_priority: number;
  won_last_30_days: number;
  lost_last_30_days: number;
  estimated_pipeline: string;
  average_score: number;
  funnel: {
    status: LeadStatus;
    label: string;
    total: number;
    estimated_value: string;
  }[];
  by_source: {
    source: string;
    total: number;
    high_priority: number;
    estimated_value: string;
    average_score: number;
  }[];
}

export interface LeadScoreResponse {
  lead_id: string;
  score: number;
  category: LeadCategory;
  method: string;
  version: string;
  reasons: ScoreReason[];
  risks: string[];
  next_step: string;
  suggested_message: string | null;
  sources: string[];
}

/* ------------------------------------------------------------ importações -- */

export interface CanonicalFieldInfo {
  field: string;
  label: string;
  required: boolean;
  synonyms: string[];
}

export interface ColumnMapping {
  id: string;
  source_column: string;
  target_field: string | null;
  confidence: number;
  is_manual: boolean;
  sample_values: string[];
}

export interface ImportJob {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sheet_name: string | null;
  status: ImportStatus;
  detected_columns: string[];
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  imported_rows: number;
  updated_rows: number;
  stats: Record<string, unknown>;
  error_message: string | null;
  validated_at: string | null;
  committed_at: string | null;
  created_at: string;
  created_by_id: string | null;
  mappings?: ColumnMapping[];
  available_sheets?: string[];
}

export interface RowIssue {
  field: string;
  label: string;
  message: string;
  value: string | null;
}

export interface PreviewRow {
  row_number: number;
  raw: Record<string, string | null>;
  normalized: Record<string, string | number | null>;
  status: RowStatus;
  errors: RowIssue[];
  warnings: RowIssue[];
}

export interface MappingSuggestion {
  source_column: string;
  target_field: string | null;
  confidence: number;
  reason: string;
  needs_review: boolean;
}

export interface ImportPreview {
  import_id: string;
  status: ImportStatus;
  headers: string[];
  available_sheets: string[];
  active_sheet: string | null;
  delimiter: string | null;
  encoding: string | null;
  total_rows_in_file: number;
  mapping: Record<string, string | null>;
  suggestions: MappingSuggestion[];
  unmapped_columns: string[];
  missing_required_fields: string[];
  rows: PreviewRow[];
  canonical_fields: CanonicalFieldInfo[];
}

export interface ValidationSummary {
  import_id: string;
  status: ImportStatus;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  warning_rows: number;
  unique_keys: number;
  errors_by_field: Record<string, number>;
  top_errors: { field: string; message: string; count: number }[];
  fill_rate: Record<string, number>;
  dedupe_criteria: Record<string, number>;
  monthly_value_sum: string;
  mapped_fields: string[];
  unmapped_columns: string[];
}

export interface CommitResult {
  import_id: string;
  status: ImportStatus;
  created_customers: number;
  updated_customers: number;
  created_plans: number;
  created_renewals: number;
  skipped_invalid: number;
  skipped_duplicates: number;
  committed_at: string | null;
  message: string;
}

export interface RowError {
  row_number: number;
  status: RowStatus;
  raw_data: Record<string, string | null>;
  normalized_data: Record<string, unknown>;
  errors: RowIssue[];
  warnings: RowIssue[];
  duplicate_of_row: number | null;
}

export interface ImportReport {
  job: ImportJob;
  validation: ValidationSummary | null;
  sample_errors: RowError[];
  recommendations: string[];
}

/* ---------------------------------------------------- base de conhecimento -- */

export interface KnowledgeDocument {
  id: string;
  title: string;
  original_filename: string | null;
  mime_type: string;
  size_bytes: number;
  char_count: number;
  chunk_count: number;
  status: DocumentStatus;
  tags: string[];
  source_label: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  excerpt: string;
  score: number;
  page_hint: string | null;
  matched_terms: string[];
}

export interface SearchResponse {
  query: string;
  engine: string;
  total: number;
  hits: SearchHit[];
  notice: string | null;
}

/* ------------------------------------------------------------------ IA ----- */

export interface AssistantFact {
  label: string;
  value: string | number | null;
  kind: string;
  source: string;
}

export interface AssistantSource {
  type: string;
  title: string;
  locator: string | null;
  document_id: string | null;
  score: number | null;
  excerpt: string | null;
}

export interface AssistantAnswer {
  question: string;
  intent: string;
  intent_label: string;
  answer: string;
  has_evidence: boolean;
  facts: AssistantFact[];
  sources: AssistantSource[];
  tables: Record<string, Record<string, unknown>[]>;
  reasoning: string[];
  recommendation: string | null;
  suggestions: string[];
  trace: Record<string, unknown>;
  generated_at: string;
}

export interface ProviderInfo {
  name: string;
  default_model: string;
  supports_json: boolean;
  is_mock: boolean;
  configured: boolean;
  active: boolean;
}

export interface AssistantConfig {
  active_provider: string;
  active_model: string;
  is_mock: boolean;
  providers: ProviderInfo[];
  search_engine: string;
  suggestions: string[];
  no_evidence_message: string;
}

export interface LeadClassification {
  score: number;
  category: LeadCategory;
  reasons: string[];
  risks: string[];
  next_action: string;
  suggested_message: string;
  summary: string;
}

export interface LeadClassificationResponse {
  lead_id: string;
  classification: LeadClassification;
  rules_score: number;
  rules_version: string;
  agreement: string;
  sources: AssistantSource[];
  trace: Record<string, unknown>;
  generated_at: string;
}

export interface RenewalSummaryResponse {
  summary: string;
  has_evidence: boolean;
  indicators: RenewalOverview;
  critical_customers: {
    customer_name: string;
    plan_name: string | null;
    due_date: string;
    days_until_due: number;
    amount: string;
    status: RenewalStatus;
    reason: string;
  }[];
  recommended_actions: string[];
  sources: AssistantSource[];
  trace: Record<string, unknown>;
  generated_at: string;
}

export interface MessageDraftResponse {
  draft: string;
  purpose: string;
  target: Record<string, unknown>;
  sources: AssistantSource[];
  trace: Record<string, unknown>;
  disclaimer: string;
  generated_at: string;
}

export interface LlmUsage {
  id: string;
  feature: string;
  provider: string;
  model: string;
  prompt_version: string;
  status: string;
  input_summary: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  duration_ms: number;
  attempts: number;
  error: string | null;
  agent_run_id: string | null;
  created_at: string;
}

/* -------------------------------------------------------------- agentes ---- */

export interface AgentInfo {
  key: string;
  name: string;
  description: string;
  allowed_tools: string[];
  max_steps: number;
}

export interface AgentStep {
  index: number;
  tool: string;
  arguments: Record<string, unknown>;
  rationale: string;
  status: string;
  duration_ms: number;
  observation: Record<string, unknown> | null;
  error: string | null;
}

export interface AgentRunResponse {
  run_id: string;
  agent_name: string;
  status: AgentRunStatus;
  answer: string;
  has_evidence: boolean;
  tools_used: string[];
  steps: AgentStep[];
  sources: Record<string, unknown>[];
  duration_ms: number;
  correlation_id: string;
  error: string | null;
  trace: Record<string, unknown>;
}

/* --------------------------------------------------------- integrações ----- */

export interface IntegrationStatus {
  inbound_signature_required: boolean;
  signature_header: string;
  idempotency_header: string;
  event_header: string;
  organization_header: string;
  outbound_url_configured: boolean;
  outbound_url: string | null;
  inbound_endpoints: {
    event: string;
    method: string;
    path: string;
    description: string;
  }[];
  outbound_events: { event: string; description: string }[];
  totals: Record<string, number>;
}

export interface WebhookEvent {
  id: string;
  direction: WebhookDirection;
  event_type: string;
  idempotency_key: string;
  signature_valid: boolean;
  status: WebhookStatus;
  attempts: number;
  target_url: string | null;
  payload: Record<string, unknown>;
  response: Record<string, unknown>;
  error: string | null;
  processed_at: string | null;
  created_at: string;
}

/* ------------------------------------------------------------- auditoria --- */

export interface AuditEvent {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor_email: string;
  actor_role: string;
  summary: string;
  meta: Record<string, unknown>;
  correlation_id: string;
  ip_address: string | null;
  created_at: string;
}

export interface AuditActionSummary {
  action: string;
  total: number;
}
