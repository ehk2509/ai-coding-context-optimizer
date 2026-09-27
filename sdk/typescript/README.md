# @acco-ai/sdk

Typed, dependency-free JavaScript/TypeScript middleware client for ACCO.

The TypeScript SDK intentionally does **not** reimplement ACCO's optimization
algorithms. Start the local Python engine:

```bash
pip install acco
acco sdk-serve .
```

Then call it from a custom agent:

```ts
import { AccoClient } from "@acco-ai/sdk";

const acco = new AccoClient();
const middleware = acco.middleware("anthropic");

const prepared = await middleware.beforeRequest(requestBody);
const optimizedTool = await middleware.afterToolResult({
  text: rawToolOutput,
  query: userPrompt,
  command: "pytest -q",
});

if (optimizedTool.recovery_handle) {
  const exact = await middleware.recover(optimizedTool.recovery_handle);
}

const browser = await middleware.afterBrowserResult({
  text: rawAccessibilitySnapshot,
  query: userPrompt,
  options: { format_hint: "auto", min_tokens: 400 },
});
```

The service binds to loopback by default. Do not expose it on a network without
your own authentication and transport controls.

For clients that accept a custom `fetch`, intercept the provider boundary
without changing its base URL:

```ts
const providerFetch = acco.interceptFetch("openai");
```

Only JSON model requests are eligible. Accepted transforms target provider tool
schemas and historical tool/function results; current user/source context is not
rewritten. If ACCO accepts no transform, the original request bytes are passed
through. If the local bridge is unavailable, the interceptor fails open by
default.

## Browser/context payloads

`optimizeBrowser()` and `afterBrowserResult()` use ACCO's Python browser
optimizer for caller-supplied HTML, accessibility/ARIA text snapshots, and
browser-shaped JSON. The transform keeps focused semantic/actionable context and
returns a `tsr_...` handle whenever exact source bytes were omitted.

```ts
const focused = await acco.optimizeBrowser(
  rawSnapshot,
  "checkout save",
  { format_hint: "auto", min_tokens: 400 },
);
```

This is context optimization only: ACCO does not navigate, fetch URLs, execute
page JavaScript, or inspect screenshots.


## Optional RAG / API / database middleware

These are context-compression adapters, not data-access clients. ACCO never runs
retrieval, network requests, SQL, or database connections for these methods.

```ts
const rag = await acco.rag().optimize(
  retrievedDocuments,
  question,
  { max_documents: 8 },
);

const api = await acco.api().optimize(apiJson, question);

const rows = await acco.database().optimize(
  databaseRows,
  "blocked",
  ["id", "name", "status"],
  { max_rows: 20 },
);
```

The compressed `value` is intended for LLM/model context. It is not guaranteed
to preserve the original business payload schema after compression. When
`changed=true`, `recovery_handle` restores the exact deterministic
canonical-JSON representation accepted by ACCO.
