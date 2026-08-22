"use client";

import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  apiRequest,
  type Dataset,
  type EvaluationResult,
  type EvaluationRun,
  type EvaluationRunDetail,
  type ModelVariant,
  type Project,
} from "./api";

const MODEL_PRESETS = [
  { label: "Qwen 3.6 27B", value: "groq/qwen/qwen3.6-27b" },
  { label: "GPT OSS 20B", value: "groq/openai/gpt-oss-20b" },
];

const shortId = (value: string) => value.slice(0, 8);
const formatDate = (value: string) =>
  new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
const formatPercent = (value: number) => `${Math.round(value * 100)}%`;
const formatCost = (value: number | string | null) =>
  `$${Number(value ?? 0).toFixed(6)}`;

type FailureHandler = (caught: unknown, fallback: string) => void;

type VariantDraft = {
  name: string;
  model: string;
  temperature: string;
  maxTokens: string;
  timeoutSeconds: string;
  maxRetries: string;
  systemPrompt: string;
};

const emptyVariantDraft: VariantDraft = {
  name: "",
  model: MODEL_PRESETS[0].value,
  temperature: "0",
  maxTokens: "1024",
  timeoutSeconds: "30",
  maxRetries: "2",
  systemPrompt: "",
};

export function ModelWorkspace({
  token,
  project,
  variants,
  onVariantsChange,
  onFailure,
  onNotice,
}: {
  token: string;
  project: Project;
  variants: ModelVariant[];
  onVariantsChange: (variants: ModelVariant[]) => void;
  onFailure: FailureHandler;
  onNotice: (message: string) => void;
}) {
  const [editing, setEditing] = useState<ModelVariant | null>(null);
  const [draft, setDraft] = useState<VariantDraft>(emptyVariantDraft);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);

  function openCreate() {
    setEditing(null);
    setDraft(emptyVariantDraft);
    setShowModal(true);
  }

  function openEdit(variant: ModelVariant) {
    setEditing(variant);
    setDraft({
      name: variant.name,
      model: variant.model,
      temperature: String(variant.temperature),
      maxTokens: variant.max_tokens === null ? "" : String(variant.max_tokens),
      timeoutSeconds: String(variant.timeout_seconds),
      maxRetries: String(variant.max_retries),
      systemPrompt: variant.system_prompt ?? "",
    });
    setShowModal(true);
  }

  async function saveVariant(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    const payload = {
      name: draft.name.trim(),
      model: draft.model.trim(),
      provider: "litellm",
      temperature: Number(draft.temperature),
      max_tokens: draft.maxTokens ? Number(draft.maxTokens) : null,
      timeout_seconds: Number(draft.timeoutSeconds),
      max_retries: Number(draft.maxRetries),
      system_prompt: draft.systemPrompt.trim() || null,
    };
    try {
      const saved = await apiRequest<ModelVariant>(
        editing
          ? `/api/v1/variants/${editing.id}`
          : `/api/v1/projects/${project.id}/variants`,
        {
          method: editing ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
        token,
      );
      onVariantsChange(
        editing
          ? variants.map((variant) => (variant.id === saved.id ? saved : variant))
          : [...variants, saved],
      );
      setShowModal(false);
      onNotice(editing ? "Model variant updated." : "Model variant created.");
    } catch (caught) {
      onFailure(caught, "Could not save model variant.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteVariant(variant: ModelVariant) {
    if (!window.confirm(`Delete model variant “${variant.name}”?`)) return;
    setSaving(true);
    try {
      await apiRequest<void>(
        `/api/v1/variants/${variant.id}`,
        { method: "DELETE" },
        token,
      );
      onVariantsChange(variants.filter((entry) => entry.id !== variant.id));
      onNotice("Model variant deleted.");
    } catch (caught) {
      onFailure(caught, "Could not delete model variant.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="section-intro panel">
        <div>
          <span className="panel-kicker">MODEL CONFIGURATION</span>
          <h2>Model variants</h2>
          <p>
            Save reusable provider settings, then compare two or more variants in
            one evaluation run.
          </p>
        </div>
        <button className="primary-button" onClick={openCreate} type="button">
          ＋ New model
        </button>
      </section>

      {variants.length ? (
        <section className="variant-grid">
          {variants.map((variant) => (
            <article className="panel variant-card" key={variant.id}>
              <div className="variant-card-head">
                <span className="model-orb">M</span>
                <span className="provider-pill">{variant.provider}</span>
              </div>
              <h3>{variant.name}</h3>
              <code>{variant.model}</code>
              <dl>
                <div><dt>Temperature</dt><dd>{variant.temperature}</dd></div>
                <div><dt>Max tokens</dt><dd>{variant.max_tokens ?? "provider default"}</dd></div>
                <div><dt>Timeout</dt><dd>{variant.timeout_seconds}s</dd></div>
                <div><dt>Retries</dt><dd>{variant.max_retries}</dd></div>
              </dl>
              {variant.system_prompt && (
                <p className="system-prompt">“{variant.system_prompt}”</p>
              )}
              <div className="variant-actions">
                <button className="secondary-button" onClick={() => openEdit(variant)} type="button">Edit</button>
                <button className="danger-button" disabled={saving} onClick={() => void deleteVariant(variant)} type="button">Delete</button>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="panel stage-empty">
          <span>M</span>
          <h2>No model variants yet</h2>
          <p>Add Qwen and GPT OSS configurations before launching a comparison.</p>
          <button className="primary-button" onClick={openCreate} type="button">＋ Add first model</button>
        </section>
      )}

      {showModal && (
        <Dialog titleId="variant-title" onClose={() => setShowModal(false)} wide>
          <span className="panel-kicker">MODEL VARIANT</span>
          <h2 id="variant-title">{editing ? "Edit model" : "Add a model"}</h2>
          <p>LiteLLM sends these settings to Groq. Your API key stays in the backend environment.</p>
          <form onSubmit={saveVariant}>
            <div className="form-grid">
              <label>
                Display name
                <input maxLength={200} required value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Qwen baseline" />
              </label>
              <label>
                Model ID
                <input list="model-presets" maxLength={300} required value={draft.model} onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))} />
                <datalist id="model-presets">{MODEL_PRESETS.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}</datalist>
              </label>
            </div>
            <div className="form-grid three-fields">
              <label>Temperature<input min="0" max="2" step="0.1" required type="number" value={draft.temperature} onChange={(event) => setDraft((current) => ({ ...current, temperature: event.target.value }))} /></label>
              <label>Max tokens<input min="1" type="number" value={draft.maxTokens} onChange={(event) => setDraft((current) => ({ ...current, maxTokens: event.target.value }))} /></label>
              <label>Timeout, sec<input min="1" step="1" required type="number" value={draft.timeoutSeconds} onChange={(event) => setDraft((current) => ({ ...current, timeoutSeconds: event.target.value }))} /></label>
            </div>
            <label>Retries<input min="0" max="10" step="1" required type="number" value={draft.maxRetries} onChange={(event) => setDraft((current) => ({ ...current, maxRetries: event.target.value }))} /></label>
            <label>System prompt <small>optional</small><textarea rows={3} value={draft.systemPrompt} onChange={(event) => setDraft((current) => ({ ...current, systemPrompt: event.target.value }))} placeholder="Answer clearly and concisely." /></label>
            <DialogActions label={editing ? "Save changes" : "Add model"} onCancel={() => setShowModal(false)} saving={saving} />
          </form>
        </Dialog>
      )}
    </>
  );
}

type RunComparisonDetails = {
  baseline: EvaluationRunDetail;
  candidate: EvaluationRunDetail;
};

export function RunWorkspace({
  token,
  project,
  datasets,
  variants,
  runs,
  onRunChange,
  onFailure,
  onNotice,
}: {
  token: string;
  project: Project;
  datasets: Dataset[];
  variants: ModelVariant[];
  runs: EvaluationRun[];
  onRunChange: (run: EvaluationRun) => void;
  onFailure: FailureHandler;
  onNotice: (message: string) => void;
}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runs[0]?.id ?? null);
  const [detail, setDetail] = useState<EvaluationRunDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const [variantIds, setVariantIds] = useState<string[]>(variants.map((variant) => variant.id));
  const [concurrency, setConcurrency] = useState("3");
  const [saving, setSaving] = useState(false);
  const [showCompare, setShowCompare] = useState(false);
  const [baselineRunId, setBaselineRunId] = useState("");
  const [candidateRunId, setCandidateRunId] = useState("");
  const [comparison, setComparison] = useState<RunComparisonDetails | null>(null);
  const [loadingComparison, setLoadingComparison] = useState(false);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );
  const completedRuns = useMemo(
    () => runs
      .filter((run) => run.status === "completed")
      .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
    [runs],
  );

  const loadDetail = useCallback(async (runId: string, quiet = false) => {
    if (!quiet) setLoadingDetail(true);
    try {
      const next = await apiRequest<EvaluationRunDetail>(`/api/v1/runs/${runId}`, {}, token);
      setDetail(next);
      onRunChange(next);
      return next;
    } catch (caught) {
      onFailure(caught, "Could not load evaluation results.");
      return null;
    } finally {
      if (!quiet) setLoadingDetail(false);
    }
  }, [onFailure, onRunChange, token]);

  useEffect(() => {
    if (!selectedRunId) return;
    const timer = window.setTimeout(() => void loadDetail(selectedRunId), 0);
    return () => window.clearTimeout(timer);
  }, [loadDetail, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || !selectedRun || !["pending", "running"].includes(selectedRun.status)) return;
    const timer = window.setInterval(() => void loadDetail(selectedRunId, true), 1500);
    return () => window.clearInterval(timer);
  }, [loadDetail, selectedRun, selectedRunId]);

  function openCreateRun() {
    setDatasetId(datasets[0]?.id ?? "");
    setVariantIds(variants.map((variant) => variant.id));
    setConcurrency("3");
    setShowCreate(true);
  }

  function openRunComparison() {
    const candidate = completedRuns.find((run) => run.id === selectedRunId) ?? completedRuns[0];
    const baseline = completedRuns.find((run) => run.id !== candidate?.id);
    if (!candidate || !baseline) return;
    setCandidateRunId(candidate.id);
    setBaselineRunId(baseline.id);
    setShowCompare(true);
  }

  async function compareRuns(event: FormEvent) {
    event.preventDefault();
    if (!baselineRunId || !candidateRunId || baselineRunId === candidateRunId) return;
    setLoadingComparison(true);
    try {
      const [baseline, candidate] = await Promise.all([
        apiRequest<EvaluationRunDetail>(`/api/v1/runs/${baselineRunId}`, {}, token),
        apiRequest<EvaluationRunDetail>(`/api/v1/runs/${candidateRunId}`, {}, token),
      ]);
      setComparison({ baseline, candidate });
      setShowCompare(false);
      onNotice("Run comparison loaded.");
    } catch (caught) {
      onFailure(caught, "Could not compare evaluation runs.");
    } finally {
      setLoadingComparison(false);
    }
  }

  function toggleVariant(variantId: string) {
    setVariantIds((current) => current.includes(variantId)
      ? current.filter((id) => id !== variantId)
      : [...current, variantId]);
  }

  async function createRun(event: FormEvent) {
    event.preventDefault();
    if (!datasetId || !variantIds.length) return;
    setSaving(true);
    try {
      const run = await apiRequest<EvaluationRun>(
        "/api/v1/runs",
        {
          method: "POST",
          body: JSON.stringify({
            project_id: project.id,
            dataset_id: datasetId,
            variant_ids: variantIds,
            concurrency: Number(concurrency),
          }),
        },
        token,
      );
      onRunChange(run);
      setDetail(null);
      setSelectedRunId(run.id);
      setShowCreate(false);
      onNotice("Evaluation scheduled. Live progress is now updating.");
    } catch (caught) {
      onFailure(caught, "Could not start evaluation.");
    } finally {
      setSaving(false);
    }
  }

  async function cancelRun() {
    if (!selectedRunId) return;
    setSaving(true);
    try {
      const run = await apiRequest<EvaluationRun>(
        `/api/v1/runs/${selectedRunId}/cancel`,
        { method: "POST" },
        token,
      );
      onRunChange(run);
      await loadDetail(run.id, true);
      onNotice("Evaluation cancellation requested.");
    } catch (caught) {
      onFailure(caught, "Could not cancel evaluation.");
    } finally {
      setSaving(false);
    }
  }

  const progress = detail?.total_tasks
    ? Math.round((detail.completed_tasks / detail.total_tasks) * 100)
    : 0;
  const canCreate = datasets.length > 0 && variants.length > 0;

  return (
    <>
      <section className="section-intro panel">
        <div>
          <span className="panel-kicker">LIVE EVALUATION</span>
          <h2>Evaluation runs</h2>
          <p>Run every test case against selected models and compare quality, speed, tokens, and errors.</p>
        </div>
        <div className="section-actions">
          <button className="secondary-button" disabled={completedRuns.length < 2} onClick={openRunComparison} title={completedRuns.length < 2 ? "Complete at least two runs to compare them" : undefined} type="button">⇄ Compare runs</button>
          <button className="primary-button" disabled={!canCreate} onClick={openCreateRun} type="button">↗ New evaluation</button>
        </div>
      </section>
      {!canCreate && (
        <div className="workflow-warning">Create at least one dataset with test cases and one model variant before starting a run.</div>
      )}
      {comparison && <RunComparisonPanel baseline={comparison.baseline} candidate={comparison.candidate} datasets={datasets} onClose={() => setComparison(null)} />}

      <section className="run-workspace">
        <aside className="panel run-list-panel">
          <div className="panel-head"><div><span className="panel-kicker">HISTORY</span><h2>Runs</h2></div><span className="period-pill">{runs.length}</span></div>
          <div className="run-list">
            {runs.length ? runs.map((run) => {
              const runProgress = run.total_tasks ? Math.round(run.completed_tasks / run.total_tasks * 100) : 0;
              return (
                <button className={`run-list-item${selectedRunId === run.id ? " active" : ""}`} key={run.id} onClick={() => { setDetail(null); setSelectedRunId(run.id); }} type="button">
                  <span><strong>run_{shortId(run.id)}</strong><small>{formatDate(run.created_at)}</small></span>
                  <Status status={run.status} />
                  <i><b style={{ width: `${runProgress}%` }} /></i>
                  <small>{run.completed_tasks}/{run.total_tasks} tasks</small>
                </button>
              );
            }) : <div className="mini-run-empty"><span>↗</span><strong>No runs yet</strong><p>Your comparisons will appear here.</p></div>}
          </div>
        </aside>

        <article className="panel run-detail-panel">
          {loadingDetail && !detail ? (
            <div className="inline-loading"><span /> Loading evaluation…</div>
          ) : detail ? (
            <>
              <header className="run-detail-head">
                <div><span className="panel-kicker">RUN_{shortId(detail.id).toUpperCase()}</span><h2>Model comparison</h2><p>{detail.completed_tasks} of {detail.total_tasks} tasks processed · concurrency {detail.concurrency}</p></div>
                <div className="run-head-actions"><Status status={detail.status} />{["pending", "running"].includes(detail.status) && <button className="danger-button" disabled={saving} onClick={() => void cancelRun()} type="button">Cancel run</button>}</div>
              </header>
              <div className="run-progress"><span><i style={{ width: `${progress}%` }} /></span><strong>{progress}%</strong></div>
              {detail.error && <div className="run-error">{detail.error}</div>}
              <RunAnalytics detail={detail} variants={variants} />
              <SummaryTable detail={detail} />
              <ResultsTable key={detail.id} results={detail.results} variants={variants} />
            </>
          ) : (
            <div className="detail-empty"><span>←</span><strong>Select an evaluation run</strong><p>Open a run to inspect live progress and model-by-model results.</p></div>
          )}
        </article>
      </section>

      {showCreate && (
        <Dialog titleId="new-run-title" onClose={() => setShowCreate(false)} wide>
          <span className="panel-kicker">NEW EVALUATION</span>
          <h2 id="new-run-title">Compare model variants</h2>
          <p>Each selected model receives every test case in the dataset. Progress and partial results appear live.</p>
          <form onSubmit={createRun}>
            <label>
              Dataset
              <select required value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
                {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
              </select>
            </label>
            <fieldset className="variant-picker">
              <legend>Models to compare</legend>
              {variants.map((variant) => (
                <div className="variant-option" key={variant.id}><input aria-label={`Select ${variant.name}`} checked={variantIds.includes(variant.id)} id={`run-variant-${variant.id}`} onChange={() => toggleVariant(variant.id)} type="checkbox" /><span><strong>{variant.name}</strong><small>{variant.model}</small></span></div>
              ))}
            </fieldset>
            <label>Parallel workers <small>1–20</small><input min="1" max="20" required type="number" value={concurrency} onChange={(event) => setConcurrency(event.target.value)} /></label>
            <DialogActions disabled={!variantIds.length || !datasetId} label="Start evaluation" onCancel={() => setShowCreate(false)} saving={saving} />
          </form>
        </Dialog>
      )}
      {showCompare && (
        <Dialog titleId="compare-runs-title" onClose={() => setShowCompare(false)} wide>
          <span className="panel-kicker">RUN-TO-RUN ANALYTICS</span>
          <h2 id="compare-runs-title">Compare completed runs</h2>
          <p>Use an earlier run as the baseline, then measure how the candidate changed across every primary metric.</p>
          <form onSubmit={compareRuns}>
            <div className="form-grid">
              <label>Baseline <small>before</small><select required value={baselineRunId} onChange={(event) => setBaselineRunId(event.target.value)}>{completedRuns.map((run) => <option key={run.id} value={run.id}>run_{shortId(run.id)} · {formatDate(run.created_at)}</option>)}</select></label>
              <label>Candidate <small>after</small><select required value={candidateRunId} onChange={(event) => setCandidateRunId(event.target.value)}>{completedRuns.map((run) => <option key={run.id} value={run.id}>run_{shortId(run.id)} · {formatDate(run.created_at)}</option>)}</select></label>
            </div>
            {baselineRunId === candidateRunId && <div className="comparison-form-warning">Choose two different completed runs.</div>}
            <DialogActions disabled={!baselineRunId || !candidateRunId || baselineRunId === candidateRunId} label="Compare runs" onCancel={() => setShowCompare(false)} saving={loadingComparison} />
          </form>
        </Dialog>
      )}
    </>
  );
}

type ComparisonValues = {
  quality: number;
  latency: number;
  tokens: number;
  cost: number;
  errors: number;
};

type RunComparisonMetric = {
  key: keyof ComparisonValues;
  label: string;
  higherIsBetter: boolean;
  format: (value: number) => string;
  formatDelta: (value: number) => string;
};

const signed = (value: number, suffix = "") => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(Math.round(value)).toLocaleString()}${suffix}`;
const signedCost = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}$${Math.abs(value).toFixed(6)}`;

const runComparisonMetrics: RunComparisonMetric[] = [
  { key: "quality", label: "Quality", higherIsBetter: true, format: formatPercent, formatDelta: (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value * 100).toFixed(1)} pp` },
  { key: "latency", label: "Latency", higherIsBetter: false, format: (value) => `${Math.round(value)} ms`, formatDelta: (value) => signed(value, " ms") },
  { key: "tokens", label: "Tokens", higherIsBetter: false, format: (value) => Math.round(value).toLocaleString(), formatDelta: signed },
  { key: "cost", label: "Cost", higherIsBetter: false, format: (value) => formatCost(value), formatDelta: signedCost },
  { key: "errors", label: "Errors", higherIsBetter: false, format: (value) => String(Math.round(value)), formatDelta: signed },
];

function average(values: number[]) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
}

function valuesFromRun(run: EvaluationRunDetail): ComparisonValues {
  return {
    quality: average(run.summary.map((summary) => summary.average_quality)),
    latency: average(run.summary.map((summary) => summary.average_latency_ms)),
    tokens: run.summary.reduce((total, summary) => total + summary.total_tokens, 0),
    cost: run.summary.reduce((total, summary) => total + Number(summary.total_estimated_cost), 0),
    errors: run.summary.reduce((total, summary) => total + summary.error_count, 0),
  };
}

function valuesFromSummary(summary: EvaluationRunDetail["summary"][number]): ComparisonValues {
  return {
    quality: summary.average_quality,
    latency: summary.average_latency_ms,
    tokens: summary.total_tokens,
    cost: Number(summary.total_estimated_cost),
    errors: summary.error_count,
  };
}

function deltaTone(metric: RunComparisonMetric, delta: number) {
  if (Math.abs(delta) < 0.0000001) return "neutral";
  return (metric.higherIsBetter ? delta > 0 : delta < 0) ? "improved" : "regressed";
}

function deltaMarker(tone: ReturnType<typeof deltaTone>) {
  return tone === "improved" ? "✓" : tone === "regressed" ? "!" : "=";
}

function RunComparisonPanel({ baseline, candidate, datasets, onClose }: { baseline: EvaluationRunDetail; candidate: EvaluationRunDetail; datasets: Dataset[]; onClose: () => void }) {
  const baselineValues = valuesFromRun(baseline);
  const candidateValues = valuesFromRun(candidate);
  const baselineSummaries = new Map(baseline.summary.map((summary) => [summary.variant_name, summary]));
  const candidateSummaries = new Map(candidate.summary.map((summary) => [summary.variant_name, summary]));
  const variantNames = [...new Set([...baselineSummaries.keys(), ...candidateSummaries.keys()])].sort();
  const sameVariantSet = baselineSummaries.size === candidateSummaries.size && [...baselineSummaries.keys()].every((name) => candidateSummaries.has(name));
  const baselineDataset = datasets.find((dataset) => dataset.id === baseline.dataset_id)?.name ?? `Dataset ${shortId(baseline.dataset_id)}`;
  const candidateDataset = datasets.find((dataset) => dataset.id === candidate.dataset_id)?.name ?? `Dataset ${shortId(candidate.dataset_id)}`;

  return (
    <section className="panel run-comparison-panel" aria-labelledby="run-comparison-title">
      <header className="run-comparison-head">
        <div><span className="panel-kicker">RUN-TO-RUN COMPARISON</span><h2 id="run-comparison-title">What changed?</h2><p>Candidate values are compared against the selected baseline.</p></div>
        <button className="comparison-close" onClick={onClose} type="button" aria-label="Close run comparison">×</button>
      </header>
      <div className="comparison-route" aria-label="Compared evaluation runs">
        <div><small>BASELINE</small><strong>run_{shortId(baseline.id)}</strong><span>{baselineDataset} · {formatDate(baseline.created_at)}</span></div>
        <i>→</i>
        <div><small>CANDIDATE</small><strong>run_{shortId(candidate.id)}</strong><span>{candidateDataset} · {formatDate(candidate.created_at)}</span></div>
      </div>
      {baseline.dataset_id !== candidate.dataset_id && <div className="comparison-dataset-warning">⚠ These runs use different datasets. Metric changes may reflect different test cases, not only model or prompt improvements.</div>}
      {!sameVariantSet && <div className="comparison-dataset-warning">⚠ These runs use different model sets. Overall token, cost, and error totals are not directly comparable; use the model-by-model table below.</div>}
      <div className="comparison-metric-grid">
        {runComparisonMetrics.map((metric) => {
          const baselineValue = baselineValues[metric.key];
          const candidateValue = candidateValues[metric.key];
          const delta = candidateValue - baselineValue;
          const tone = deltaTone(metric, delta);
          return (
            <article className="comparison-metric-card" key={metric.key}>
              <div><span>{metric.label}</span><strong aria-label={`${tone}: ${metric.formatDelta(delta)}`} className={`delta-badge delta-${tone}`}>{deltaMarker(tone)} {metric.formatDelta(delta)}</strong></div>
              <dl><div><dt>Before</dt><dd>{metric.format(baselineValue)}</dd></div><i>→</i><div><dt>After</dt><dd>{metric.format(candidateValue)}</dd></div></dl>
            </article>
          );
        })}
      </div>
      <section className="comparison-models">
        <div className="comparison-title"><div><span className="panel-kicker">VARIANT DELTAS</span><h3>Model-by-model changes</h3></div><small>{variantNames.length} variants</small></div>
        <div className="table-wrap"><table className="run-comparison-table"><thead><tr><th>Variant</th>{runComparisonMetrics.map((metric) => <th key={metric.key}>{metric.label}</th>)}</tr></thead><tbody>
          {variantNames.map((variantName) => {
            const baselineSummary = baselineSummaries.get(variantName);
            const candidateSummary = candidateSummaries.get(variantName);
            const before = baselineSummary ? valuesFromSummary(baselineSummary) : null;
            const after = candidateSummary ? valuesFromSummary(candidateSummary) : null;
            return <tr key={variantName}><td><strong>{variantName}</strong><small>{before && after ? "Compared in both runs" : before ? "Removed from candidate" : "New in candidate"}</small></td>{runComparisonMetrics.map((metric) => <ComparisonDeltaCell after={after} before={before} key={metric.key} metric={metric} />)}</tr>;
          })}
        </tbody></table></div>
      </section>
    </section>
  );
}

function ComparisonDeltaCell({ before, after, metric }: { before: ComparisonValues | null; after: ComparisonValues | null; metric: RunComparisonMetric }) {
  if (!before || !after) return <td><span className="comparison-unavailable">{after ? "New" : "Removed"}</span></td>;
  const beforeValue = before[metric.key];
  const afterValue = after[metric.key];
  const delta = afterValue - beforeValue;
  const tone = deltaTone(metric, delta);
  return <td><strong aria-label={`${tone}: ${metric.formatDelta(delta)}`} className={`delta-badge delta-${tone}`}>{deltaMarker(tone)} {metric.formatDelta(delta)}</strong><small>{metric.format(beforeValue)} → {metric.format(afterValue)}</small></td>;
}

type AnalyticsMetric = {
  label: string;
  note: string;
  tone: "green" | "blue" | "purple" | "orange" | "red";
  higherIsBetter: boolean;
  value: (summary: EvaluationRunDetail["summary"][number]) => number;
  format: (value: number) => string;
};

const analyticsMetrics: AnalyticsMetric[] = [
  {
    label: "Quality",
    note: "Higher is better",
    tone: "green",
    higherIsBetter: true,
    value: (summary) => summary.average_quality,
    format: formatPercent,
  },
  {
    label: "Latency",
    note: "Lower is better",
    tone: "blue",
    higherIsBetter: false,
    value: (summary) => summary.average_latency_ms,
    format: (value) => `${Math.round(value)} ms`,
  },
  {
    label: "Tokens",
    note: "Total usage",
    tone: "purple",
    higherIsBetter: false,
    value: (summary) => summary.total_tokens,
    format: (value) => Math.round(value).toLocaleString(),
  },
  {
    label: "Estimated cost",
    note: "Lower is better",
    tone: "orange",
    higherIsBetter: false,
    value: (summary) => Number(summary.total_estimated_cost),
    format: (value) => formatCost(value),
  },
  {
    label: "Errors",
    note: "Provider failures",
    tone: "red",
    higherIsBetter: false,
    value: (summary) => summary.error_count,
    format: (value) => String(Math.round(value)),
  },
];

function RunAnalytics({ detail, variants }: { detail: EvaluationRunDetail; variants: ModelVariant[] }) {
  const variantNames = new Map(variants.map((variant) => [variant.id, variant.name]));
  const completedNames = new Set(
    detail.results.map((result) => variantNames.get(result.variant_id)).filter((name): name is string => Boolean(name)),
  );
  const summaries = detail.summary.filter((summary) => completedNames.has(summary.variant_name));

  return (
    <section className="analytics-section" aria-labelledby="analytics-title">
      <div className="comparison-title analytics-title">
        <div><span className="panel-kicker">LIVE ANALYTICS</span><h3 id="analytics-title">Performance snapshot</h3></div>
        <small>{summaries.length ? `${summaries.length} models with results` : "Waiting for results"}</small>
      </div>
      {summaries.length ? (
        <div className="analytics-grid">
          {analyticsMetrics.map((metric) => {
            const values = summaries.map(metric.value);
            const maximum = Math.max(...values, 0);
            const best = metric.higherIsBetter ? Math.max(...values) : Math.min(...values);
            return (
              <article className={`analytics-chart chart-${metric.tone}`} key={metric.label} role="img" aria-label={`${metric.label} comparison. ${metric.note}.`}>
                <header><div><strong>{metric.label}</strong><small>{metric.note}</small></div><span>{metric.higherIsBetter ? "↑" : "↓"}</span></header>
                <div className="analytics-rows">
                  {summaries.map((summary) => {
                    const value = metric.value(summary);
                    const width = maximum > 0 ? Math.max(2, value / maximum * 100) : 0;
                    const isBest = value === best;
                    return (
                      <div className={`analytics-row${isBest ? " best" : ""}`} key={summary.variant_name} aria-label={`${summary.variant_name}: ${metric.format(value)}${isBest ? ", best result" : ""}`}>
                        <div><span>{summary.variant_name}</span><strong>{metric.format(value)}</strong></div>
                        <i><b style={{ width: `${width}%` }} /></i>
                      </div>
                    );
                  })}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="analytics-empty"><span /><p>Charts will appear after the first model response is saved.</p></div>
      )}
    </section>
  );
}

function SummaryTable({ detail }: { detail: EvaluationRunDetail }) {
  return (
    <section className="comparison-section">
      <div className="comparison-title"><div><span className="panel-kicker">AGGREGATE METRICS</span><h3>Model leaderboard</h3></div><small>{detail.summary.length} variants</small></div>
      <div className="table-wrap"><table className="summary-table"><thead><tr><th>Variant</th><th>Quality</th><th>Exact</th><th>Keyword</th><th>Latency</th><th>Tokens</th><th>Cost</th><th>Errors</th></tr></thead><tbody>
        {detail.summary.length ? detail.summary.map((summary) => <tr key={summary.variant_name}><td><strong>{summary.variant_name}</strong></td><td><strong className="quality-value">{formatPercent(summary.average_quality)}</strong></td><td>{formatPercent(summary.average_exact_match)}</td><td>{formatPercent(summary.average_keyword_score)}</td><td>{Math.round(summary.average_latency_ms)} ms</td><td>{summary.total_tokens.toLocaleString()}</td><td>{formatCost(summary.total_estimated_cost)}</td><td>{summary.error_count}</td></tr>) : <tr><td className="table-empty" colSpan={8}>{["pending", "running"].includes(detail.status) ? "Waiting for the first completed task…" : "No summary data is available."}</td></tr>}
      </tbody></table></div>
    </section>
  );
}

type ResultStatusFilter = "all" | "successful" | "errors" | "low-quality";
type ResultSort = "default" | "quality-asc" | "quality-desc" | "latency-asc" | "latency-desc" | "tokens-asc" | "tokens-desc";

function resultQuality(result: EvaluationResult) {
  return result.metrics
    ? (result.metrics.exact_match + result.metrics.normalized_exact_match + result.metrics.keyword_score) / 3
    : null;
}

function compareNullable(left: number | null, right: number | null, direction: 1 | -1) {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return (left - right) * direction;
}

function ResultsTable({ results, variants }: { results: EvaluationResult[]; variants: ModelVariant[] }) {
  const [search, setSearch] = useState("");
  const [variantId, setVariantId] = useState("all");
  const [statusFilter, setStatusFilter] = useState<ResultStatusFilter>("all");
  const [sort, setSort] = useState<ResultSort>("default");
  const names = useMemo(() => new Map(variants.map((variant) => [variant.id, variant.name])), [variants]);
  const resultVariants = useMemo(() => {
    const ids = [...new Set(results.map((result) => result.variant_id))];
    return ids.map((id) => ({ id, name: names.get(id) ?? results.find((result) => result.variant_id === id)?.model ?? id })).sort((left, right) => left.name.localeCompare(right.name));
  }, [names, results]);
  const visibleResults = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return results
      .map((result, index) => ({ result, index }))
      .filter(({ result }) => {
        if (variantId !== "all" && result.variant_id !== variantId) return false;
        if (query && !result.input.toLocaleLowerCase().includes(query)) return false;
        if (statusFilter === "successful" && result.error) return false;
        if (statusFilter === "errors" && !result.error) return false;
        if (statusFilter === "low-quality") {
          const quality = resultQuality(result);
          if (quality === null || quality >= 0.67) return false;
        }
        return true;
      })
      .sort((left, right) => {
        switch (sort) {
          case "quality-asc": return compareNullable(resultQuality(left.result), resultQuality(right.result), 1) || left.index - right.index;
          case "quality-desc": return compareNullable(resultQuality(left.result), resultQuality(right.result), -1) || left.index - right.index;
          case "latency-asc": return (left.result.latency_ms - right.result.latency_ms) || left.index - right.index;
          case "latency-desc": return (right.result.latency_ms - left.result.latency_ms) || left.index - right.index;
          case "tokens-asc": return compareNullable(left.result.total_tokens, right.result.total_tokens, 1) || left.index - right.index;
          case "tokens-desc": return compareNullable(left.result.total_tokens, right.result.total_tokens, -1) || left.index - right.index;
          default: return left.index - right.index;
        }
      })
      .map(({ result }) => result);
  }, [results, search, sort, statusFilter, variantId]);
  const hasActiveFilters = Boolean(search) || variantId !== "all" || statusFilter !== "all" || sort !== "default";

  function clearFilters() {
    setSearch("");
    setVariantId("all");
    setStatusFilter("all");
    setSort("default");
  }

  return (
    <section className="comparison-section results-section">
      <div className="comparison-title"><div><span className="panel-kicker">TASK OUTPUTS</span><h3>Individual results</h3></div><small>{visibleResults.length} of {results.length} shown</small></div>
      {results.length > 0 && (
        <div className="result-controls" aria-label="Result filters">
          <label className="result-search"><span>Search prompt</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a test case…" /></label>
          <label><span>Model</span><select value={variantId} onChange={(event) => setVariantId(event.target.value)}><option value="all">All models</option>{resultVariants.map((variant) => <option key={variant.id} value={variant.id}>{variant.name}</option>)}</select></label>
          <label><span>Result</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ResultStatusFilter)}><option value="all">All results</option><option value="successful">Successful</option><option value="errors">Errors only</option><option value="low-quality">Quality below 67%</option></select></label>
          <label><span>Sort by</span><select value={sort} onChange={(event) => setSort(event.target.value as ResultSort)}><option value="default">Dataset order</option><option value="quality-asc">Quality: lowest first</option><option value="quality-desc">Quality: highest first</option><option value="latency-desc">Latency: slowest first</option><option value="latency-asc">Latency: fastest first</option><option value="tokens-desc">Tokens: highest first</option><option value="tokens-asc">Tokens: lowest first</option></select></label>
          {hasActiveFilters && <button className="clear-filter-button" onClick={clearFilters} type="button">× Clear</button>}
        </div>
      )}
      <div className="table-wrap"><table className="result-table"><thead><tr><th>Model</th><th>Prompt & output</th><th>Quality</th><th>Latency</th><th>Tokens</th><th>Retries / error</th></tr></thead><tbody>
        {visibleResults.length ? visibleResults.map((result) => {
          const quality = resultQuality(result);
          return <tr className={result.error ? "result-row-error" : quality !== null && quality < 0.67 ? "result-row-weak" : undefined} key={result.id}><td><strong>{names.get(result.variant_id) ?? result.model}</strong><small>{result.model}</small></td><td><details><summary>{result.input}</summary><div className="result-copy"><span>Expected</span><p>{result.expected_output || "—"}</p><span>Model output</span><p>{result.output || "—"}</p></div></details></td><td>{quality === null ? "—" : formatPercent(quality)}</td><td>{Math.round(result.latency_ms)} ms</td><td>{result.total_tokens ?? "—"}</td><td>{result.error ? <span className="result-error" title={result.error}>Error · {result.error}</span> : `${result.retry_count} retries`}</td></tr>;
        }) : results.length ? <tr><td className="table-empty filtered-empty" colSpan={6}><strong>No matching results</strong><span>Change the filters or search phrase to see more tasks.</span><button className="text-button" onClick={clearFilters} type="button">Clear filters →</button></td></tr> : <tr><td className="table-empty" colSpan={6}>No task results have been saved yet.</td></tr>}
      </tbody></table></div>
    </section>
  );
}

function Status({ status }: { status: EvaluationRun["status"] }) {
  return <span className={`status status-${status}`}>{status}</span>;
}

function Dialog({ children, onClose, titleId, wide = false }: { children: ReactNode; onClose: () => void; titleId: string; wide?: boolean }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section aria-labelledby={titleId} aria-modal="true" className={`modal${wide ? " modal-wide" : ""}`} role="dialog"><button aria-label="Close dialog" className="modal-close" onClick={onClose} type="button">×</button>{children}</section></div>;
}

function DialogActions({ disabled = false, label, onCancel, saving }: { disabled?: boolean; label: string; onCancel: () => void; saving: boolean }) {
  return <div className="modal-actions"><button className="secondary-button" onClick={onCancel} type="button">Cancel</button><button className="primary-button" disabled={disabled || saving} type="submit">{saving ? "Saving…" : label}</button></div>;
}
