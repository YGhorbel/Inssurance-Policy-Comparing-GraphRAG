# Runners

Concrete benchmark runners live here. Each subclasses
`evaluation.harness.Runner` and sets a unique `mode` string used in the
output filename and the JSONL `mode` field.

A runner must implement `run_one(query: Query) -> QueryResult`. The base
class provides `run(query_set_path)` which iterates a YAML query set and
writes a JSONL file under `evaluation/results/` named
`<mode>_<stem>_<UTC-timestamp>.jsonl`.

Phase 1 ships the contract only. Phase 5 will add concrete runners that
invoke the live MCP `/mcp` endpoint or `agents.graph_rag.fusion.GraphRAG`
directly. No benchmark corpora are downloaded yet.
