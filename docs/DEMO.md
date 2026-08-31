# Evalflow Demo Guide

This guide presents the complete product workflow in about five minutes. It
uses real provider APIs and the repository's deterministic sample benchmark;
there is no fake-model or hidden demo execution path.

## Before the Demo

1. Start the full stack with `docker compose up --build`.
2. Open `http://localhost:3000`, create an account, and sign in.
3. Open **AI Providers** and save at least one provider API key.
4. Keep in mind that running the benchmark makes billable provider requests.

## Guided Product Tour

1. Create a project named **Portfolio comparison**.
2. Open **Datasets**, select **Import file**, and upload
   `examples/portfolio-benchmark.json`.
3. Open **Models** and add two model variants. Attach each variant to its saved
   provider credential. The models may come from different providers.
4. Open **Evaluation runs**, select the imported dataset and both variants, set
   concurrency to `4`, and start the evaluation.
5. Show live task progress, then open the finished run.
6. Compare quality, latency, token usage, estimated cost, and provider errors
   in the model leaderboard and charts.
7. Search individual results, filter by model or status, change sorting, and
   move between server-side result pages.
8. Select a second completed run to show metric deltas, then export JSON or CSV.

## What the Benchmark Covers

The 15 test cases cover short factual answers, arithmetic, basic logic,
translation, transformation, ordering, and strict structured output. Prompts
request deterministic answers so exact-match metrics are meaningful. Keyword
coverage still gives partial credit when a model adds harmless formatting.

The sample contains no provider credentials and can be committed or shared
safely. Evalflow never sends its `expected_output` or `keywords` fields to the
model; they are used only after generation to calculate metrics.

## Resetting the Demo

Delete the project from the UI and create it again. Project ownership and
cascade rules remove its datasets, variants, runs, and results without
affecting another account. Saved provider credentials belong to the account,
not the project, so they can be reused.
