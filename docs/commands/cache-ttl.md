# cache-ttl

Inspect provider-observed prompt-cache lifetime evidence.

```bash
acco cache-ttl .
acco cache-ttl . --json
```

ACCO learns only from explicit provider cache counters. Missing cache counters are
not treated as misses. A qualified TTL estimate requires repeated observed cache
hits plus an exact-prefix post-hit miss. The report keeps the observed hit lower
bound and expiry upper bound visible rather than presenting a guessed universal
provider TTL.
