// JSON-lines stdio bridge to the vendored Meterless H-MEM reference engine.
//
//   node --experimental-transform-types --no-warnings hmem_bridge.mjs [--persist-dir DIR] [--clock-ms N] [--actor NAME]
//
// One request per stdin line: {"id": 1, "method": "query", "params": {...}}
// One response per stdout line: {"id": 1, "result": ...} or {"id": 1, "error": "..."}
// Every call goes to a real `HMEM` instance; nothing here stores or ranks memories itself.

import { createInterface } from "node:readline";
import { readFileSync } from "node:fs";
import { HMEM } from "./hmem/src/index.ts";

const args = process.argv.slice(2);
const option = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const persistDir = option("--persist-dir");
const fixedClock = option("--clock-ms");
const engine = new HMEM({
  persistDir,
  actor: option("--actor") ?? "sentry-ai",
  clock: fixedClock ? () => Number(fixedClock) : Date.now,
});
const upstream = JSON.parse(readFileSync(new URL("./hmem/upstream-package.json", import.meta.url), "utf-8"));

// Embeddings are large and internal; callers get every other field of the canonical record.
const record = ({ embedding, ...rest }) => rest;

const methods = {
  info: () => ({
    engine: "H-MEM",
    package: upstream.name,
    version: upstream.version,
    persistent: Boolean(persistDir),
    records: engine.store.all().length,
  }),
  add: (p) => record(engine.add({
    content: p.content,
    source: p.source,
    type: p.type,
    layer: p.layer,
    tags: p.tags,
    confidence: p.confidence,
    provenance: p.provenance ? { ...p.provenance, learnedAt: engine.clock() } : undefined,
  })),
  query: (p) => {
    const result = engine.query(p.query, { topN: p.topN, threshold: p.threshold });
    return {
      memories: result.memories.map((m) => ({ memory: record(m.memory), relevance: m.relevance })),
      context: result.context,
      trace: result.trace,
    };
  },
  feedback: (p) => {
    engine.feedback(p.memoryId, p.kind);
    return record(engine.store.get(p.memoryId));
  },
  get: (p) => {
    const found = engine.store.get(p.memoryId);
    return found ? record(found) : null;
  },
  scan_conflicts: () => engine.conflicts.scan(),
  history: (p) => engine.ledger.history(p.memoryId),
  stats: () => ({ records: engine.store.all().length, ledger: engine.ledger.stats() }),
};

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on("line", (line) => {
  if (!line.trim()) return;
  let id = null;
  try {
    const request = JSON.parse(line);
    id = request.id ?? null;
    const method = methods[request.method];
    if (!method) throw new Error(`unknown method ${request.method}`);
    process.stdout.write(JSON.stringify({ id, result: method(request.params ?? {}) }) + "\n");
  } catch (error) {
    process.stdout.write(JSON.stringify({ id, error: String(error?.message ?? error) }) + "\n");
  }
});
