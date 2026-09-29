export type JsonObject = Record<string, unknown>;

export interface AccoClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface ProviderFetchOptions {
  fetchImpl?: typeof fetch;
  failOpen?: boolean;
}

export interface ProviderOptimization {
  schema: number;
  body: JsonObject;
  metadata: JsonObject;
}

export interface ContextOptimization {
  schema: number;
  text: string;
  kind: string;
  changed: boolean;
  original_tokens: number;
  output_tokens: number;
  recovery_handle: string | null;
  metadata: JsonObject;
}

export interface BrowserOptimization {
  schema: number;
  text: string;
  changed: boolean;
  original_tokens: number;
  output_tokens: number;
  recovery_handle: string | null;
  matched_terms: string[];
  kind: "html" | "ax" | "json" | "text";
  source_items: number;
  shown_items: number;
  interactive_items: number;
}

export interface BrowserResultInput {
  text: string;
  query?: string;
  options?: JsonObject;
}

export interface OutputOptimization {
  schema: number;
  text: string;
  processor: string;
  changed: boolean;
  compressed: boolean;
  failed: boolean;
  recovered_lines: string[];
  original_tokens: number;
  output_tokens: number;
  recovery_handle: string | null;
}

export interface StructuredOptimization {
  schema: number;
  domain: "rag" | "api" | "database";
  format: "json";
  value: unknown;
  changed: boolean;
  original_tokens: number;
  output_tokens: number;
  recovery_handle: string | null;
  metadata: JsonObject;
}

export interface RagMiddleware {
  optimize(
    documents: unknown[],
    query?: string,
    options?: JsonObject,
  ): Promise<StructuredOptimization>;
  recover(handle: string): Promise<RecoveryResult>;
}

export interface ApiPayloadMiddleware {
  optimize(
    payload: JsonObject | unknown[],
    query?: string,
    options?: JsonObject,
  ): Promise<StructuredOptimization>;
  recover(handle: string): Promise<RecoveryResult>;
}

export interface DatabaseMiddleware {
  optimize(
    rows: unknown[],
    query?: string,
    columns?: string[] | null,
    options?: JsonObject,
  ): Promise<StructuredOptimization>;
  recover(handle: string): Promise<RecoveryResult>;
}

export interface ExecutionResult {
  schema: number;
  language: "restricted-python";
  files: string[];
  input_bytes: number;
  result_bytes: number;
  elapsed_ms: number;
  timeout_seconds: number;
  out_of_context: true;
  truncated: boolean;
  result: unknown | null;
  preview?: string;
  recovery_handle: string | null;
}

export interface BatchExecutionJob {
  id?: string;
  code?: string;
  code_file?: string;
  files: string[];
}

export interface BatchExecutionResult {
  schema: number;
  language: "restricted-python";
  job_count: number;
  input_bytes: number;
  result_bytes: number;
  elapsed_ms: number;
  out_of_context: true;
  truncated: boolean;
  results: Array<{ id: string } & ExecutionResult> | null;
  preview?: string;
  recovery_handle: string | null;
}

export interface SessionLedgerEvent {
  id: number;
  recorded_at: number;
  session: string | null;
  turn: number | null;
  kind: string;
  subject: string;
  summary: string;
  path: string | null;
  status: string | null;
  metadata: JsonObject;
}

export interface SessionLedgerResult {
  schema: number;
  count: number;
  events: SessionLedgerEvent[];
  query?: string;
  mode?: "fts5" | "like";
}

export interface RecoveryResult {
  schema: number;
  handle: string;
  content_type: string;
  encoding: "utf-8" | "base64";
  payload: string;
  size_bytes: number;
  metadata: JsonObject;
  created_at: number;
  last_accessed_at: number | null;
  access_count: number;
}

export interface ContextBudgetPlan {
  total_tokens: number;
  task: string;
  complexity_tier: string;
  risk_level: string;
  allocations: Record<string, number>;
  weights: Record<string, number>;
  observed_tokens: Record<string, number>;
  reasons: string[];
}

export interface ModelRouteDecision {
  [key: string]: unknown;
  selected_model: string | null;
  current_model: string | null;
  action: "recommend" | "keep" | "route" | "manual";
}

export interface ToolFieldLearningReport {
  schema: number;
  tools: number;
  fields: Array<{
    tool: string;
    field_path: string;
    exposures: number;
    retrievals: number;
    confidence: number;
    last_seen: number;
  }>;
  privacy: string;
}

export interface CacheTtlReport {
  schema: number;
  estimates: Array<{
    provider: string;
    model: string;
    observations: number;
    hits: number;
    misses: number;
    hit_lower_bound_seconds: number | null;
    expiry_upper_bound_seconds: number | null;
    learned_ttl_seconds: number | null;
    qualified: boolean;
    evidence_basis: string;
  }>;
  policy: string;
}

export interface OutputHoldoutReport {
  schema: number;
  experiment: string;
  matched_epoch_weight: number;
  measured_output_token_reduction: number | null;
  ci95: [number, number] | null;
  strata: JsonObject[];
  claim_boundary: string;
}

export interface ObservabilityReport {
  schema: number;
  window_days: number;
  providers: Record<string, JsonObject>;
  frameworks: Record<string, JsonObject>;
  cache_ttl: Record<string, number>;
  output_holdout: Record<string, number>;
  evidence: string;
}

export interface ToolResultInput {
  text: string;
  query?: string;
  command?: string;
  options?: JsonObject;
}

export interface AccoMiddleware {
  beforeRequest(
    body: JsonObject,
    options?: JsonObject,
  ): Promise<ProviderOptimization>;
  afterToolResult(result: ToolResultInput): Promise<ContextOptimization>;
  afterBrowserResult(result: BrowserResultInput): Promise<BrowserOptimization>;
  route(
    prompt: string,
    options?: JsonObject,
  ): Promise<ModelRouteDecision>;
  recover(handle: string): Promise<RecoveryResult>;
}

export declare class AccoSdkError extends Error {
  readonly status: number;
  readonly payload: unknown;
  constructor(message: string, status: number, payload: unknown);
}

export declare class AccoClient {
  readonly baseUrl: string;
  readonly timeoutMs: number;
  constructor(options?: AccoClientOptions);
  health(): Promise<JsonObject>;
  optimizeRequest(
    provider: string,
    body: JsonObject,
    options?: JsonObject,
  ): Promise<ProviderOptimization>;
  optimizeContext(
    text: string,
    query?: string,
    command?: string,
    options?: JsonObject,
  ): Promise<ContextOptimization>;
  optimizeBrowser(
    text: string,
    query?: string,
    options?: JsonObject,
  ): Promise<BrowserOptimization>;
  optimizeOutput(
    text: string,
    command?: string,
    exitCode?: number | null,
    options?: JsonObject,
  ): Promise<OutputOptimization>;
  optimizeRag(
    documents: unknown[],
    query?: string,
    options?: JsonObject,
  ): Promise<StructuredOptimization>;
  optimizeApiPayload(
    payload: JsonObject | unknown[],
    query?: string,
    options?: JsonObject,
  ): Promise<StructuredOptimization>;
  optimizeDatabaseRows(
    rows: unknown[],
    query?: string,
    columns?: string[] | null,
    options?: JsonObject,
  ): Promise<StructuredOptimization>;
  execute(
    code: string,
    files: string[],
    options?: JsonObject,
  ): Promise<ExecutionResult>;
  executeFile(
    programFile: string,
    files: string[],
    options?: JsonObject,
  ): Promise<ExecutionResult & { program_file: string }>;
  batchExecute(
    jobs: BatchExecutionJob[],
    options?: JsonObject,
  ): Promise<BatchExecutionResult>;
  sessionSearch(
    query: string,
    options?: {
      kinds?: string[];
      session?: string;
      limit?: number;
    },
  ): Promise<SessionLedgerResult>;
  sessionRecent(
    options?: {
      kinds?: string[];
      session?: string;
      limit?: number;
    },
  ): Promise<SessionLedgerResult>;
  planContextBudget(
    prompt: string,
    totalTokens: number,
    options?: JsonObject,
  ): Promise<ContextBudgetPlan>;
  routeModel(
    prompt: string,
    options?: JsonObject,
  ): Promise<ModelRouteDecision>;
  recover(handle: string): Promise<RecoveryResult>;
  observability(days?: number): Promise<ObservabilityReport>;
  cacheTtl(): Promise<CacheTtlReport>;
  outputHoldout(bootstrapSamples?: number): Promise<OutputHoldoutReport>;
  toolFields(limit?: number): Promise<ToolFieldLearningReport>;
  interceptFetch(
    provider: string,
    options?: ProviderFetchOptions,
  ): typeof fetch;
  rag(): RagMiddleware;
  api(): ApiPayloadMiddleware;
  database(): DatabaseMiddleware;
  middleware(provider: string): AccoMiddleware;
}
