# tool-fields

Inspect local structured tool-field importance learned from selective recovery.

```bash
acco tool-fields .
acco tool-fields . --limit 25 --json
```

The learner stores bounded tool identities, structural JSON paths, exposure
counts, retrieval counts, and timestamps. It does not store the corresponding
field values. A field becomes a compaction hint only after repeated local
exposure and selective-recovery evidence.
