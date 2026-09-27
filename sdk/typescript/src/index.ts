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

export class AccoSdkError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "AccoSdkError";
    this.status = status;
    this.payload = payload;
  }
}

export class AccoClient {
  readonly baseUrl: string;
  readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: AccoClientOptions = {}) {
    const baseUrl = (options.baseUrl ?? "http://127.0.0.1:8770").replace(/\/+$/, "");
    const parsed = new URL(baseUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new TypeError("ACCO SDK baseUrl must use http or https");
    }
    this.baseUrl = baseUrl;
    this.timeoutMs = options.timeoutMs ?? 120_000;
    if (!Number.isFinite(this.timeoutMs) || this.timeoutMs <= 0) {
      throw new TypeError("ACCO SDK timeoutMs must be positive");
    }
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    body?: JsonObject,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(this.baseUrl + path, {
        method,
        headers: body ? { "content-type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      const raw = await response.text();
      let payload: unknown = {};
      if (raw) {
        try {
          payload = JSON.parse(raw);
        } catch {
          throw new AccoSdkError("ACCO SDK returned invalid JSON", response.status, raw);
        }
      }
      if (!response.ok) {
        const detail =
          payload && typeof payload === "object" && "message" in payload
            ? String((payload as { message?: unknown }).message ?? "")
            : "";
        throw new AccoSdkError(
          detail || `ACCO SDK request failed with HTTP ${response.status}`,
          response.status,
          payload,
        );
      }
      return payload as T;
    } finally {
      clearTimeout(timer);
    }
  }

  health(): Promise<JsonObject> {
    return this.request<JsonObject>("GET", "/v1/health");
  }

  optimizeRequest(
    provider: string,
    body: JsonObject,
    options: JsonObject = {},
  ): Promise<ProviderOptimization> {
    return this.request("POST", "/v1/provider/optimize", {
      provider,
      body,
      options,
    });
  }

  optimizeContext(
    text: string,
    query = "",
    command = "",
    options: JsonObject = {},
  ): Promise<ContextOptimization> {
    return this.request("POST", "/v1/context/optimize", {
      text,
      query,
      command,
      options,
    });
  }

  optimizeBrowser(
    text: string,
    query = "",
    options: JsonObject = {},
  ): Promise<BrowserOptimization> {
    return this.request("POST", "/v1/browser/optimize", {
      text,
      query,
      options,
    });
  }

  optimizeOutput(
    text: string,
    command = "",
    exitCode: number | null = null,
    options: JsonObject = {},
  ): Promise<OutputOptimization> {
    const payload: JsonObject = { text, command, options };
    if (exitCode !== null) payload.exit_code = exitCode;
    return this.request("POST", "/v1/output/optimize", payload);
  }

  optimizeRag(
    documents: unknown[],
    query = "",
    options: JsonObject = {},
  ): Promise<StructuredOptimization> {
    return this.request("POST", "/v1/middleware/rag", {
      documents,
      query,
      options,
    });
  }

  optimizeApiPayload(
    payload: JsonObject | unknown[],
    query = "",
    options: JsonObject = {},
  ): Promise<StructuredOptimization> {
    return this.request("POST", "/v1/middleware/api", {
      payload,
      query,
      options,
    });
  }

  optimizeDatabaseRows(
    rows: unknown[],
    query = "",
    columns: string[] | null = null,
    options: JsonObject = {},
  ): Promise<StructuredOptimization> {
    const payload: JsonObject = {
      rows,
      query,
      options,
    };
    if (columns !== null) payload.columns = columns;
    return this.request("POST", "/v1/middleware/database", payload);
  }

  planContextBudget(
    prompt: string,
    totalTokens: number,
    options?: JsonObject,
  ): Promise<ContextBudgetPlan> {
    return this.request("POST", "/v1/context-budget", {
      prompt,
      total_tokens: totalTokens,
      options,
    });
  }

  routeModel(
    prompt: string,
    options: JsonObject = {},
  ): Promise<ModelRouteDecision> {
    return this.request("POST", "/v1/route", { prompt, options });
  }

  recover(handle: string): Promise<RecoveryResult> {
    return this.request("POST", "/v1/recover", { handle });
  }

  interceptFetch(
    provider: string,
    options: ProviderFetchOptions = {},
  ): typeof fetch {
    if (!provider.trim()) throw new TypeError("provider must be nonempty");
    const upstream = options.fetchImpl ?? fetch;
    const failOpen = options.failOpen ?? true;
    const client = this;

    return (async function accoProviderFetch(
      input: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> {
      const request = input instanceof Request ? input : null;
      const method = String(init?.method ?? request?.method ?? "GET").toUpperCase();
      if (method === "GET" || method === "HEAD") {
        return upstream(input, init);
      }

      const headers = new Headers(request?.headers);
      if (init?.headers) {
        new Headers(init.headers).forEach((value, key) => headers.set(key, value));
      }
      const contentType = headers.get("content-type") ?? "";
      if (!contentType.toLowerCase().includes("json")) {
        return upstream(input, init);
      }

      let raw: string | null = null;
      if (typeof init?.body === "string") {
        raw = init.body;
      } else if (init?.body != null) {
        return upstream(input, init);
      } else if (request) {
        try {
          raw = await request.clone().text();
        } catch {
          return upstream(input, init);
        }
      }
      if (!raw) return upstream(input, init);

      let body: unknown;
      try {
        body = JSON.parse(raw);
      } catch {
        return upstream(input, init);
      }
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        return upstream(input, init);
      }

      let optimized: ProviderOptimization;
      try {
        optimized = await client.optimizeRequest(
          provider,
          body as JsonObject,
        );
      } catch (error) {
        if (failOpen) return upstream(input, init);
        throw error;
      }

      if (optimized.metadata.changed !== true) {
        return upstream(input, init);
      }
      headers.delete("content-length");
      const encoded = JSON.stringify(optimized.body);
      if (request && init?.body == null) {
        return upstream(
          new Request(request, {
            ...init,
            body: encoded,
            headers,
          }),
        );
      }
      return upstream(input, {
        ...init,
        headers,
        body: encoded,
      });
    }) as typeof fetch;
  }

  rag(): RagMiddleware {
    return {
      optimize: (documents: unknown[], query = "", options: JsonObject = {}) =>
        this.optimizeRag(documents, query, options),
      recover: (handle: string) => this.recover(handle),
    };
  }

  api(): ApiPayloadMiddleware {
    return {
      optimize: (
        payload: JsonObject | unknown[],
        query = "",
        options: JsonObject = {},
      ) => this.optimizeApiPayload(payload, query, options),
      recover: (handle: string) => this.recover(handle),
    };
  }

  database(): DatabaseMiddleware {
    return {
      optimize: (
        rows: unknown[],
        query = "",
        columns: string[] | null = null,
        options: JsonObject = {},
      ) => this.optimizeDatabaseRows(rows, query, columns, options),
      recover: (handle: string) => this.recover(handle),
    };
  }

  middleware(provider: string): AccoMiddleware {
    if (!provider.trim()) throw new TypeError("provider must be nonempty");
    return {
      beforeRequest: (body: JsonObject, options: JsonObject = {}) =>
        this.optimizeRequest(provider, body, options),
      afterToolResult: (result: ToolResultInput) =>
        this.optimizeContext(
          result.text,
          result.query ?? "",
          result.command ?? "",
          result.options ?? {},
        ),
      afterBrowserResult: (result: BrowserResultInput) =>
        this.optimizeBrowser(
          result.text,
          result.query ?? "",
          result.options ?? {},
        ),
      route: (prompt: string, options: JsonObject = {}) =>
        this.routeModel(prompt, options),
      recover: (handle: string) => this.recover(handle),
    };
  }
}
