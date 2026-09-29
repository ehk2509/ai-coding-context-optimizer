import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { AccoClient, AccoSdkError } from "../dist/index.js";

function withServer(handler, run) {
  return new Promise((resolve, reject) => {
    const server = http.createServer(handler);
    server.listen(0, "127.0.0.1", async () => {
      try {
        const address = server.address();
        const result = await run(`http://127.0.0.1:${address.port}`);
        server.close(() => resolve(result));
      } catch (error) {
        server.close(() => reject(error));
      }
    });
  });
}

test("typed client sends provider optimization contract", async () => {
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    assert.equal(req.url, "/v1/provider/optimize");
    assert.equal(body.provider, "anthropic");
    assert.equal(body.body.messages[0].role, "user");
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ schema: 1, body: body.body, metadata: { changed: false } }));
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });
    const result = await client.optimizeRequest("anthropic", {
      messages: [{ role: "user", content: "hello" }],
    });
    assert.equal(result.schema, 1);
    assert.equal(result.metadata.changed, false);
  });
});

test("middleware binds provider and exposes tool optimization", async () => {
  const paths = [];
  await withServer(async (req, res) => {
    paths.push(req.url);
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    res.writeHead(200, { "content-type": "application/json" });
    if (req.url === "/v1/provider/optimize") {
      assert.equal(body.provider, "openai");
      res.end(JSON.stringify({ schema: 1, body: body.body, metadata: {} }));
    } else {
      assert.equal(body.command, "pytest -q");
      res.end(JSON.stringify({
        schema: 1,
        text: body.text,
        kind: "plain",
        changed: false,
        original_tokens: 1,
        output_tokens: 1,
        recovery_handle: null,
        metadata: {},
      }));
    }
  }, async (baseUrl) => {
    const middleware = new AccoClient({ baseUrl }).middleware("openai");
    await middleware.beforeRequest({ input: [] });
    await middleware.afterToolResult({ text: "ok", command: "pytest -q" });
  });
  assert.deepEqual(paths, ["/v1/provider/optimize", "/v1/context/optimize"]);
});

test("non-2xx responses preserve structured SDK error", async () => {
  await withServer((_req, res) => {
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "invalid_request", message: "bad payload" }));
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });
    await assert.rejects(
      () => client.recover("bad"),
      (error) =>
        error instanceof AccoSdkError &&
        error.status === 400 &&
        error.message === "bad payload",
    );
  });
});


test("browser optimizer uses the specialized SDK endpoint", async () => {
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    assert.equal(req.url, "/v1/browser/optimize");
    assert.equal(body.query, "Save order");
    assert.equal(body.options.format_hint, "ax");
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      schema: 1,
      text: '- button "Save order"',
      changed: true,
      original_tokens: 900,
      output_tokens: 20,
      recovery_handle: "tsr_test",
      matched_terms: ["save", "order"],
      kind: "ax",
      source_items: 200,
      shown_items: 10,
      interactive_items: 4,
    }));
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });
    const result = await client.optimizeBrowser(
      '- button "Save order"',
      "Save order",
      { format_hint: "ax" },
    );
    assert.equal(result.kind, "ax");
    assert.equal(result.interactive_items, 4);

    const middleware = client.middleware("openai");
    const viaMiddleware = await middleware.afterBrowserResult({
      text: '- button "Save order"',
      query: "Save order",
      options: { format_hint: "ax" },
    });
    assert.equal(viaMiddleware.kind, "ax");
  });
});

test("provider fetch interceptor optimizes JSON and fails open by default", async () => {
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (req.url === "/v1/provider/optimize") {
      assert.equal(body.provider, "openai");
      const optimized = structuredClone(body.body);
      optimized.marker = "optimized";
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({
        schema: 1,
        body: optimized,
        metadata: { changed: true },
      }));
      return;
    }
    res.writeHead(404);
    res.end();
  }, async (baseUrl) => {
    const seen = [];
    const upstream = async (input, init) => {
      seen.push({
        url: String(input),
        body: init?.body ?? null,
      });
      return new Response("ok", { status: 200 });
    };
    const client = new AccoClient({ baseUrl });
    const intercepted = client.interceptFetch("openai", { fetchImpl: upstream });
    await intercepted("https://api.openai.test/v1/responses", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ input: "hello" }),
    });
    assert.equal(JSON.parse(seen[0].body).marker, "optimized");
  });

  const failingClient = new AccoClient({
    baseUrl: "http://127.0.0.1:1",
    timeoutMs: 50,
  });
  const seen = [];
  const upstream = async (input, init) => {
    seen.push(init?.body ?? null);
    return new Response("ok", { status: 200 });
  };
  const intercepted = failingClient.interceptFetch("anthropic", {
    fetchImpl: upstream,
  });
  const original = JSON.stringify({ messages: [{ role: "user", content: "hello" }] });
  await intercepted("https://api.anthropic.test/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: original,
  });
  assert.equal(seen[0], original);
});

test("provider fetch interceptor preserves original JSON bytes on ACCO no-op", async () => {
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      schema: 1,
      body: body.body,
      metadata: { changed: false },
    }));
  }, async (baseUrl) => {
    const seen = [];
    const upstream = async (_input, init) => {
      seen.push(init?.body ?? null);
      return new Response("ok", { status: 200 });
    };
    const client = new AccoClient({ baseUrl });
    const intercepted = client.interceptFetch("openai", { fetchImpl: upstream });
    const original = '{ "input": "hello", "temperature": 0 }';
    await intercepted("https://api.openai.test/v1/responses", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: original,
    });
    assert.equal(seen[0], original);
  });
});

test("provider fetch interceptor can fail closed when explicitly requested", async () => {
  const client = new AccoClient({
    baseUrl: "http://127.0.0.1:1",
    timeoutMs: 50,
  });
  const intercepted = client.interceptFetch("openai", {
    fetchImpl: async () => new Response("unexpected"),
    failOpen: false,
  });
  await assert.rejects(
    () => intercepted("https://api.openai.test/v1/responses", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ input: "hello" }),
    }),
  );
});


test("typed domain middleware exposes RAG API and database surfaces", async () => {
  const seen = [];
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    seen.push({ path: req.url, body });
    const domain =
      req.url === "/v1/middleware/rag"
        ? "rag"
        : req.url === "/v1/middleware/api"
          ? "api"
          : "database";
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      schema: 1,
      domain,
      format: "json",
      value:
        domain === "rag"
          ? body.documents
          : domain === "api"
            ? body.payload
            : { columns: body.columns ?? [], rows: body.rows },
      changed: false,
      original_tokens: 10,
      output_tokens: 10,
      recovery_handle: null,
      metadata: {},
    }));
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });

    const rag = await client.rag().optimize(
      [{ id: "a", content: "retrieved chunk" }],
      "chunk",
      { max_documents: 4 },
    );
    assert.equal(rag.domain, "rag");

    const api = await client.api().optimize(
      { items: [{ id: 1 }] },
      "items",
    );
    assert.equal(api.domain, "api");

    const database = await client.database().optimize(
      [[1, "Ada"]],
      "Ada",
      ["id", "name"],
      { max_rows: 5 },
    );
    assert.equal(database.domain, "database");
  });

  assert.deepEqual(
    seen.map((item) => item.path),
    [
      "/v1/middleware/rag",
      "/v1/middleware/api",
      "/v1/middleware/database",
    ],
  );
  assert.deepEqual(seen[0].body.options, { max_documents: 4 });
  assert.deepEqual(seen[2].body.columns, ["id", "name"]);
  assert.deepEqual(seen[2].body.options, { max_rows: 5 });
});


test("context budget planner is exposed through the typed client", async () => {
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    assert.equal(req.url, "/v1/context-budget");
    assert.equal(body.prompt, "Debug the failing parser");
    assert.equal(body.total_tokens, 9000);
    assert.deepEqual(body.options, {
      observed_tokens: { tool_results: 2200 },
    });
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      total_tokens: 9000,
      task: "debugging",
      complexity_tier: "simple",
      risk_level: "normal",
      allocations: {
        source: 4300,
        history: 1000,
        memory: 400,
        tool_results: 1800,
        schemas: 300,
        reserve: 1200,
      },
      weights: {},
      observed_tokens: { tool_results: 2200 },
      reasons: ["task=debugging"],
    }));
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });
    const plan = await client.planContextBudget(
      "Debug the failing parser",
      9000,
      { observed_tokens: { tool_results: 2200 } },
    );
    assert.equal(plan.total_tokens, 9000);
    assert.equal(plan.task, "debugging");
    assert.equal(plan.allocations.tool_results, 1800);
  });
});


test("typed client exposes out-of-context execution", async () => {
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    assert.equal(req.url, "/v1/execute");
    assert.deepEqual(body.files, ["events.log"]);
    assert.match(body.code, /result/);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      schema: 1,
      language: "restricted-python",
      files: body.files,
      input_bytes: 10000,
      result_bytes: 24,
      elapsed_ms: 5,
      timeout_seconds: 5,
      out_of_context: true,
      truncated: false,
      result: { errors: 12 },
      recovery_handle: null,
    }));
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });
    const result = await client.execute(
      'result = {"errors": len(data["events.log"].splitlines())}',
      ["events.log"],
    );
    assert.equal(result.out_of_context, true);
    assert.equal(result.result.errors, 12);
  });
});


test("typed client exposes execute-file batch and session-ledger APIs", async () => {
  const seen = [];
  await withServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    seen.push({ path: req.url, body });
    res.writeHead(200, { "content-type": "application/json" });
    if (req.url === "/v1/execute-file") {
      res.end(JSON.stringify({
        schema: 1,
        language: "restricted-python",
        files: body.files,
        program_file: body.program_file,
        input_bytes: 10,
        result_bytes: 1,
        elapsed_ms: 1,
        timeout_seconds: 5,
        out_of_context: true,
        truncated: false,
        result: 3,
        recovery_handle: null,
      }));
    } else if (req.url === "/v1/batch-execute") {
      res.end(JSON.stringify({
        schema: 1,
        language: "restricted-python",
        job_count: body.jobs.length,
        input_bytes: 10,
        result_bytes: 10,
        elapsed_ms: 2,
        out_of_context: true,
        truncated: false,
        results: [{ id: "sum", result: 6 }],
        recovery_handle: null,
      }));
    } else {
      res.end(JSON.stringify({
        schema: 1,
        query: body.query,
        mode: "fts5",
        count: 1,
        events: [{
          id: 1,
          recorded_at: 1,
          session: "s1",
          turn: 1,
          kind: "decision",
          subject: "user-decision",
          summary: "Prefer SQLite.",
          path: null,
          status: null,
          metadata: {},
        }],
      }));
    }
  }, async (baseUrl) => {
    const client = new AccoClient({ baseUrl });
    const file = await client.executeFile("count.py", ["values.txt"]);
    const batch = await client.batchExecute([
      { id: "sum", code: "result = 6", files: ["values.txt"] },
    ]);
    const history = await client.sessionSearch("SQLite");

    assert.equal(file.program_file, "count.py");
    assert.equal(batch.job_count, 1);
    assert.equal(history.events[0].kind, "decision");
  });

  assert.deepEqual(
    seen.map((item) => item.path),
    ["/v1/execute-file", "/v1/batch-execute", "/v1/session/search"],
  );
});
