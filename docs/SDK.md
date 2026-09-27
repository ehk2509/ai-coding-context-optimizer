# Middleware SDKs

ACCO can be embedded in custom agents without routing the agent through a coding
CLI. The SDK surface deliberately reuses the same provider transform, context
router, output processors, model-routing policy, and exact-recovery store used
by ACCO's built-in integrations.

## Python: in-process engine

```python
from acco.sdk import AccoEngine

acco = AccoEngine("/path/to/project")
middleware = acco.middleware("anthropic")

prepared = middleware.before_request({
    "messages": [
        {"role": "user", "content": "Fix the failing authentication test"}
    ]
})

tool = middleware.after_tool_result(
    raw_tool_output,
    query="Fix the failing authentication test",
    command="pytest -q",
)

request_body = prepared["body"]
tool_text = tool["text"]

if tool["recovery_handle"]:
    exact = middleware.recover(tool["recovery_handle"])
    assert exact["encoding"] == "utf-8"
    raw_tool_output = exact["payload"]
```

Python callers can also use the engine directly:

```python
acco.optimize_provider_request("openai", body)
acco.optimize_context(text, query=prompt, command="rg auth")
acco.optimize_browser_context(
    browser_snapshot,
    query=prompt,
    format_hint="auto",
)
acco.optimize_output(stdout, command="pytest -q", exit_code=1)
acco.route_model(prompt, current_model="claude-sonnet-5")
acco.recover("tsr_...")
```

### Python middleware lifecycle

`AccoMiddleware` intentionally stays framework-neutral:

- `before_request(body, **options)` optimizes one provider-bound request;
- `after_tool_result(text, ...)` prepares large tool context before the next
  model call;
- `after_browser_result(text, ...)` explicitly focuses captured HTML, AX, or browser-JSON payloads when the host already knows a result came from a browser tool;
- `route(prompt, **options)` returns a deterministic model-routing decision
  for orchestrators that can choose a model;
- `recover(handle)` returns the exact source bytes represented by an accepted
  lossy transform.

The middleware does not send requests to a provider. Your agent remains in
control of provider authentication, retries, streaming, and model execution.

## Optional structured-data middleware

ACCO remains coding-agent-first. These adapters are opt-in SDK conveniences for
applications that already have RAG results, API JSON, or database query rows in
memory and want a smaller **model-context representation**.

They do not perform retrieval, embeddings, HTTP requests, SQL execution, ORM
access, database connections, authentication, or retries.

### Python

```python
acco = AccoEngine("/path/to/project")

rag = acco.rag().optimize(
    retrieved_documents,
    query=user_question,
    max_documents=8,
)

api = acco.api().optimize(
    large_json_response,
    query=user_question,
)

database = acco.database().optimize(
    rows,
    columns=["id", "name", "status"],
    query="blocked account",
    max_rows=20,
)
```

The direct equivalents are `optimize_rag()`, `optimize_api_payload()`, and
`optimize_database_rows()`.

### TypeScript

```ts
const rag = await acco.rag().optimize(
  retrievedDocuments,
  userQuestion,
  { max_documents: 8 },
);

const api = await acco.api().optimize(
  apiResponseJson,
  userQuestion,
);

const database = await acco.database().optimize(
  rows,
  "blocked account",
  ["id", "name", "status"],
  { max_rows: 20 },
);
```

Every result has the same structured contract:

- `domain`: `rag`, `api`, or `database`;
- `value`: the JSON-compatible model-context representation;
- `changed`: whether ACCO accepted a smaller lossy transform;
- `original_tokens` / `output_tokens`;
- `recovery_handle`: exact recovery of ACCO's deterministic canonical-JSON
  representation of the submitted data;
- `metadata`: counts and selection indexes only, never a second copy of the
  submitted payload.

RAG selection is deterministic and query-focused. Declared numeric
`score`, `relevance_score`, or `similarity` values are used only as
secondary evidence; ACCO does not run embeddings or invent relevance scores.

Database middleware accepts JSON object rows, or positional rows when
`columns` is supplied. It never executes the query itself. API middleware
accepts JSON objects/arrays and produces a context representation; it is **not**
a transparent business-API response rewriter.

All three surfaces use ACCO's shared structural JSON compaction, token/byte
reduction gates, and recovery store. If exact recovery cannot be persisted, the
full input representation is returned unchanged.

## Whole-context planning

Custom agents can ask ACCO to allocate one total context envelope before they
assemble a provider request:

```python
plan = acco.plan_context_budget(
    user_prompt,
    total_tokens=12000,
    observed_tokens={
        "tool_results": 2400,
        "schemas": 500,
        "memory": 300,
    },
)
source_budget = plan["allocations"]["source"]
```

TypeScript:

```ts
const plan = await acco.planContextBudget(
  userPrompt,
  12000,
  { observed_tokens: { tool_results: 2400, schemas: 500 } },
);
```

This is an orchestration contract, not a hidden context mutation. Provider
middleware can also receive `context_budget_total_tokens` in its options;
ACCO then uses only the schema/tool-result slices it can enforce safely.

## TypeScript: typed local client

The repository contains a typed package at `sdk/typescript`. It does not port
ACCO's optimization algorithms to JavaScript; that would create two engines
whose safety and recovery behavior could drift. Instead, TypeScript agents talk
to the same Python engine over a small versioned loopback API.

Start the bridge:

```bash
pip install acco
acco sdk-serve /path/to/project
```

Then use the client:

```ts
import { AccoClient } from "@acco-ai/sdk";

const acco = new AccoClient({
  baseUrl: "http://127.0.0.1:8770",
});

const middleware = acco.middleware("anthropic");

const prepared = await middleware.beforeRequest(requestBody);

const tool = await middleware.afterToolResult({
  text: rawToolOutput,
  query: userPrompt,
  command: "pytest -q",
});

const browser = await middleware.afterBrowserResult({
  text: rawAccessibilitySnapshot,
  query: userPrompt,
  options: { format_hint: "auto", min_tokens: 400 },
});

const route = await middleware.route(userPrompt, {
  current_model: "claude-sonnet-5",
});

if (tool.recovery_handle) {
  const exact = await middleware.recover(tool.recovery_handle);
}
```

The TypeScript runtime has no third-party production dependencies. The package
ships typed declarations and tests the published JavaScript runtime contract.

For provider SDKs that accept a custom `fetch` implementation, ACCO can
intercept the request boundary without changing the provider base URL:

```ts
const providerFetch = acco.interceptFetch("openai");

// Example: pass providerFetch as the SDK/client fetch implementation.
```

The interceptor touches only JSON request bodies, routes them through
`/v1/provider/optimize`, removes stale `content-length`, and then calls the
original provider fetch. If the local ACCO bridge is unavailable it fails open
to the untouched request by default; pass `{ failOpen: false }` when a caller
prefers strict failure. Non-JSON, GET, HEAD, streaming response, authentication,
retry, and provider transport semantics remain owned by the provider client.

## HTTP contract

The bridge exposes only versioned JSON endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/v1/health` | health/version/project identity |
| `POST` | `/v1/provider/optimize` | optimize provider request JSON |
| `POST` | `/v1/context/optimize` | recoverable arbitrary/tool context |
| `POST` | `/v1/browser/optimize` | focused HTML / AX / browser-JSON context |
| `POST` | `/v1/middleware/rag` | optional retrieved-document context compression |
| `POST` | `/v1/middleware/api` | optional JSON API-payload context compression |
| `POST` | `/v1/middleware/database` | optional caller-supplied row compression |
| `POST` | `/v1/output/optimize` | command-aware output optimization |
| `POST` | `/v1/context-budget` | deterministic whole-context allocation |
| `POST` | `/v1/route` | deterministic model-routing decision |
| `POST` | `/v1/recover` | exact recovery by `tsr_...` handle |

The request limit is 32 MiB. The service returns JSON only and does not log
request bodies.

## Safety and recovery guarantees

The SDK does not weaken ACCO's existing transformation rules:

1. A provider/context transform is accepted only when the result is smaller.
2. Lossy context/provider transformations require exact local recovery first.
3. SDK output compression with `recoverable=true` also fails open to the
   original text if the recovery store has insufficient capacity.
4. Browser optimization is local and caller-supplied only: it does not navigate, fetch URLs, execute page code, or process screenshot pixels. Ordinary JSON stays on the general context path.
5. Structured RAG/API/database middleware operates only on caller-supplied in-memory JSON-compatible data and does not retrieve, fetch, connect, or execute queries.
6. Model routing is the existing deterministic ACCO policy. A route decision is
   not an independent benchmark of model quality.
7. The TypeScript bridge binds to `127.0.0.1` by default.

The bridge has no built-in remote authentication because it is designed as a
local process boundary. `--allow-non-loopback` is explicit and should only be
used behind operator-provided authentication/TLS/access controls.

## Framework adapters

The first SDK release intentionally exposes neutral lifecycle primitives rather
than hard-coding LangChain, Vercel AI SDK, CrewAI, AutoGen, or another framework.
A framework adapter can map its hooks to `before_request` /
`after_tool_result` (Python) or `beforeRequest` /
`afterToolResult` (TypeScript) without changing ACCO internals.

This keeps framework-specific dependencies outside the core package and makes
future adapters thin, separately testable compatibility layers.
