import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the Evalflow authentication surface", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>Evalflow — LLM Evaluation Platform<\/title>/i);
  assert.match(html, /Evalflow/);
  assert.match(html, /Welcome back/);
  assert.match(html, /LLM EVALUATION WORKSPACE/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview/);
});

test("keeps access tokens out of browser storage and enables cookie refresh", async () => {
  const [pageSource, apiSource, authSource] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/auth-screen.tsx", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(pageSource, /sessionStorage|localStorage/);
  assert.match(apiSource, /credentials:\s*"include"/);
  assert.match(apiSource, /let refreshPromise:/);
  assert.match(apiSource, /\/api\/v1\/auth\/refresh/);
  assert.match(authSource, /email-verification\/confirm/);
  assert.match(authSource, /password-reset\/confirm/);
  assert.match(authSource, /window\.location\.hash/);
  assert.doesNotMatch(authSource, /sessionStorage|localStorage/);
});

test("discovers credential-scoped models while preserving manual entry", async () => {
  const [workspaceSource, apiSource] = await Promise.all([
    readFile(new URL("../app/evaluation-workspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
  ]);

  assert.match(
    workspaceSource,
    /provider-credentials\/\$\{draft\.credentialId\}\/models/,
  );
  assert.match(workspaceSource, /refresh=true/);
  assert.match(workspaceSource, /Refresh models/);
  assert.match(workspaceSource, /Manual model IDs remain supported/);
  assert.match(apiSource, /export type ProviderModelCatalog/);
});

test("loads large run results through server-side pages and complete exports", async () => {
  const [workspaceSource, apiSource] = await Promise.all([
    readFile(new URL("../app/evaluation-workspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
  ]);

  assert.match(workspaceSource, /include_results=false/);
  assert.match(workspaceSource, /\/results\/page/);
  assert.match(workspaceSource, /new URLSearchParams/);
  assert.match(workspaceSource, /result_status/);
  assert.match(workspaceSource, /fetchAllRunResults/);
  assert.match(workspaceSource, /<option value=\{100\}>100<\/option>/);
  assert.match(apiSource, /export type EvaluationResultPage/);
});

test("loads large datasets incrementally instead of truncating after fifty items", async () => {
  const [dashboardSource, apiSource] = await Promise.all([
    readFile(new URL("../app/dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api.ts", import.meta.url), "utf8"),
  ]);

  assert.match(dashboardSource, /\/items\/page\?limit=50/);
  assert.match(dashboardSource, /offset=\$\{itemOffset\}/);
  assert.match(dashboardSource, /Load 50 more/);
  assert.match(apiSource, /export type DatasetItemPage/);
});
