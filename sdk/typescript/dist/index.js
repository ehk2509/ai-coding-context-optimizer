export class AccoSdkError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "AccoSdkError";
    this.status = status;
    this.payload = payload;
  }
}

export class AccoClient {
  constructor(options = {}) {
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

  async request(method, path, body) {
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
      let payload = {};
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
            ? String(payload.message ?? "")
            : "";
        throw new AccoSdkError(
          detail || `ACCO SDK request failed with HTTP ${response.status}`,
          response.status,
          payload,
        );
      }
      return payload;
    } finally {
      clearTimeout(timer);
    }
  }

  health() {
    return this.request("GET", "/v1/health");
  }

  optimizeRequest(provider, body, options = {}) {
    return this.request("POST", "/v1/provider/optimize", {
      provider,
      body,
      options,
    });
  }

  optimizeContext(text, query = "", command = "", options = {}) {
    return this.request("POST", "/v1/context/optimize", {
      text,
      query,
      command,
      options,
    });
  }

  optimizeBrowser(text, query = "", options = {}) {
    return this.request("POST", "/v1/browser/optimize", {
      text,
      query,
      options,
    });
  }

  optimizeOutput(text, command = "", exitCode = null, options = {}) {
    const payload = { text, command, options };
    if (exitCode !== null) payload.exit_code = exitCode;
    return this.request("POST", "/v1/output/optimize", payload);
  }

  optimizeRag(documents, query = "", options = {}) {
    return this.request("POST", "/v1/middleware/rag", {
      documents,
      query,
      options,
    });
  }

  optimizeApiPayload(payload, query = "", options = {}) {
    return this.request("POST", "/v1/middleware/api", {
      payload,
      query,
      options,
    });
  }

  optimizeDatabaseRows(rows, query = "", columns = null, options = {}) {
    const payload = { rows, query, options };
    if (columns !== null) payload.columns = columns;
    return this.request("POST", "/v1/middleware/database", payload);
  }

  routeModel(prompt, options = {}) {
    return this.request("POST", "/v1/route", { prompt, options });
  }

  recover(handle) {
    return this.request("POST", "/v1/recover", { handle });
  }

  interceptFetch(provider, options = {}) {
    if (!provider.trim()) throw new TypeError("provider must be nonempty");
    const upstream = options.fetchImpl ?? fetch;
    const failOpen = options.failOpen ?? true;
    const client = this;

    return async function accoProviderFetch(input, init) {
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

      let raw = null;
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

      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        return upstream(input, init);
      }
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        return upstream(input, init);
      }

      let optimized;
      try {
        optimized = await client.optimizeRequest(provider, body);
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
        return upstream(new Request(request, { ...init, body: encoded, headers }));
      }
      return upstream(input, { ...init, headers, body: encoded });
    };
  }

  rag() {
    return {
      optimize: (documents, query = "", options = {}) =>
        this.optimizeRag(documents, query, options),
      recover: (handle) => this.recover(handle),
    };
  }

  api() {
    return {
      optimize: (payload, query = "", options = {}) =>
        this.optimizeApiPayload(payload, query, options),
      recover: (handle) => this.recover(handle),
    };
  }

  database() {
    return {
      optimize: (rows, query = "", columns = null, options = {}) =>
        this.optimizeDatabaseRows(rows, query, columns, options),
      recover: (handle) => this.recover(handle),
    };
  }

  middleware(provider) {
    if (!provider.trim()) throw new TypeError("provider must be nonempty");
    return {
      beforeRequest: (body, options = {}) =>
        this.optimizeRequest(provider, body, options),
      afterToolResult: (result) =>
        this.optimizeContext(
          result.text,
          result.query ?? "",
          result.command ?? "",
          result.options ?? {},
        ),
      afterBrowserResult: (result) =>
        this.optimizeBrowser(
          result.text,
          result.query ?? "",
          result.options ?? {},
        ),
      route: (prompt, options = {}) => this.routeModel(prompt, options),
      recover: (handle) => this.recover(handle),
    };
  }
}
