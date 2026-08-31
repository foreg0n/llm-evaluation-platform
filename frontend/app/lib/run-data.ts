import {
  apiRequest,
  type EvaluationResult,
  type EvaluationResultPage,
  type EvaluationRunDetail,
  type ModelVariant,
} from "../api";

export type ComparisonValues = {
  quality: number;
  latency: number;
  tokens: number;
  cost: number;
  errors: number;
};

export type RunComparisonMetric = {
  key: keyof ComparisonValues;
  label: string;
  higherIsBetter: boolean;
  format: (value: number) => string;
  formatDelta: (value: number) => string;
};

export type ExportFormat = "json" | "csv";

type CsvValue = string | number | boolean | null | undefined;

const shortId = (value: string) => value.slice(0, 8);
const formatPercent = (value: number) => `${Math.round(value * 100)}%`;
const formatCost = (value: number | string | null) =>
  `$${Number(value ?? 0).toFixed(6)}`;
const signed = (value: number, suffix = "") =>
  `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(Math.round(value)).toLocaleString()}${suffix}`;
const signedCost = (value: number) =>
  `${value > 0 ? "+" : value < 0 ? "−" : ""}$${Math.abs(value).toFixed(6)}`;

export const runComparisonMetrics: RunComparisonMetric[] = [
  {
    key: "quality",
    label: "Quality",
    higherIsBetter: true,
    format: formatPercent,
    formatDelta: (value) =>
      `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value * 100).toFixed(1)} pp`,
  },
  {
    key: "latency",
    label: "Latency",
    higherIsBetter: false,
    format: (value) => `${Math.round(value)} ms`,
    formatDelta: (value) => signed(value, " ms"),
  },
  {
    key: "tokens",
    label: "Tokens",
    higherIsBetter: false,
    format: (value) => Math.round(value).toLocaleString(),
    formatDelta: signed,
  },
  {
    key: "cost",
    label: "Cost",
    higherIsBetter: false,
    format: formatCost,
    formatDelta: signedCost,
  },
  {
    key: "errors",
    label: "Errors",
    higherIsBetter: false,
    format: (value) => String(Math.round(value)),
    formatDelta: signed,
  },
];

function average(values: number[]) {
  return values.length
    ? values.reduce((total, value) => total + value, 0) / values.length
    : 0;
}

export function valuesFromRun(run: EvaluationRunDetail): ComparisonValues {
  return {
    quality: average(run.summary.map((summary) => summary.average_quality)),
    latency: average(run.summary.map((summary) => summary.average_latency_ms)),
    tokens: run.summary.reduce(
      (total, summary) => total + summary.total_tokens,
      0,
    ),
    cost: run.summary.reduce(
      (total, summary) => total + Number(summary.total_estimated_cost),
      0,
    ),
    errors: run.summary.reduce(
      (total, summary) => total + summary.error_count,
      0,
    ),
  };
}

export function valuesFromSummary(
  summary: EvaluationRunDetail["summary"][number],
): ComparisonValues {
  return {
    quality: summary.average_quality,
    latency: summary.average_latency_ms,
    tokens: summary.total_tokens,
    cost: Number(summary.total_estimated_cost),
    errors: summary.error_count,
  };
}

export function deltaTone(metric: RunComparisonMetric, delta: number) {
  if (Math.abs(delta) < 0.0000001) return "neutral";
  return metric.higherIsBetter ? (delta > 0 ? "improved" : "regressed") : delta < 0 ? "improved" : "regressed";
}

export function deltaMarker(tone: ReturnType<typeof deltaTone>) {
  return tone === "improved" ? "✓" : tone === "regressed" ? "!" : "=";
}

export function resultQuality(result: EvaluationResult) {
  return result.metrics
    ? (result.metrics.exact_match +
        result.metrics.normalized_exact_match +
        result.metrics.keyword_score) /
        3
    : null;
}

export async function fetchAllRunResults(runId: string, token: string) {
  const results: EvaluationResult[] = [];
  const limit = 100;
  let offset = 0;

  while (true) {
    const page = await apiRequest<EvaluationResultPage>(
      `/api/v1/runs/${runId}/results/page?offset=${offset}&limit=${limit}`,
      {},
      token,
    );
    results.push(...page.items);
    if (!page.has_more) return results;
    offset += page.items.length;
    if (!page.items.length) {
      throw new Error("Result export pagination did not advance.");
    }
  }
}

function csvCell(value: CsvValue) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  const spreadsheetSafe = /^[=+\-@]/.test(value) ? `'${value}` : value;
  return `"${spreadsheetSafe.replaceAll('"', '""')}"`;
}

function toCsv(rows: CsvValue[][]) {
  return `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}

function downloadText(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function comparisonOutcome(metric: RunComparisonMetric, delta: number) {
  const tone = deltaTone(metric, delta);
  return tone === "neutral" ? "unchanged" : tone;
}

export function downloadRun(
  detail: EvaluationRunDetail,
  variants: ModelVariant[],
  format: ExportFormat,
) {
  const filename = `evalflow-run-${shortId(detail.id)}.${format}`;
  if (format === "json") {
    downloadText(
      filename,
      `${JSON.stringify(
        {
          schema_version: "1.0",
          export_type: "evaluation_run",
          exported_at: new Date().toISOString(),
          run: detail,
        },
        null,
        2,
      )}\n`,
      "application/json;charset=utf-8",
    );
    return;
  }

  const variantNames = new Map(
    variants.map((variant) => [variant.id, variant.name]),
  );
  const rows: CsvValue[][] = [
    [
      "run_id",
      "run_status",
      "dataset_id",
      "result_id",
      "dataset_item_id",
      "variant_id",
      "variant_name",
      "model",
      "provider",
      "input",
      "expected_output",
      "output",
      "exact_match",
      "normalized_exact_match",
      "keyword_score",
      "quality",
      "latency_ms",
      "input_tokens",
      "output_tokens",
      "total_tokens",
      "estimated_cost",
      "retry_count",
      "error",
      "created_at",
    ],
  ];
  detail.results.forEach((result) =>
    rows.push([
      detail.id,
      detail.status,
      detail.dataset_id,
      result.id,
      result.dataset_item_id,
      result.variant_id,
      variantNames.get(result.variant_id) ?? result.model,
      result.model,
      result.provider,
      result.input,
      result.expected_output,
      result.output,
      result.metrics?.exact_match,
      result.metrics?.normalized_exact_match,
      result.metrics?.keyword_score,
      resultQuality(result),
      result.latency_ms,
      result.input_tokens,
      result.output_tokens,
      result.total_tokens,
      result.estimated_cost === null ? null : Number(result.estimated_cost),
      result.retry_count,
      result.error,
      result.created_at,
    ]),
  );
  downloadText(filename, toCsv(rows), "text/csv;charset=utf-8");
}

function comparisonExport(
  baseline: EvaluationRunDetail,
  candidate: EvaluationRunDetail,
) {
  const baselineValues = valuesFromRun(baseline);
  const candidateValues = valuesFromRun(candidate);
  const baselineSummaries = new Map(
    baseline.summary.map((summary) => [summary.variant_name, summary]),
  );
  const candidateSummaries = new Map(
    candidate.summary.map((summary) => [summary.variant_name, summary]),
  );
  const variantNames = [
    ...new Set([...baselineSummaries.keys(), ...candidateSummaries.keys()]),
  ].sort();
  const metrics = (before: ComparisonValues, after: ComparisonValues) =>
    Object.fromEntries(
      runComparisonMetrics.map((metric) => {
        const delta = after[metric.key] - before[metric.key];
        return [
          metric.key,
          {
            baseline: before[metric.key],
            candidate: after[metric.key],
            delta,
            outcome: comparisonOutcome(metric, delta),
          },
        ];
      }),
    ) as Record<
      keyof ComparisonValues,
      {
        baseline: number;
        candidate: number;
        delta: number;
        outcome: string;
      }
    >;

  return {
    schema_version: "1.0",
    export_type: "run_comparison",
    exported_at: new Date().toISOString(),
    baseline: {
      id: baseline.id,
      dataset_id: baseline.dataset_id,
      created_at: baseline.created_at,
      summary: baseline.summary,
    },
    candidate: {
      id: candidate.id,
      dataset_id: candidate.dataset_id,
      created_at: candidate.created_at,
      summary: candidate.summary,
    },
    warnings: {
      different_datasets: baseline.dataset_id !== candidate.dataset_id,
      different_model_sets:
        baselineSummaries.size !== candidateSummaries.size ||
        [...baselineSummaries.keys()].some(
          (name) => !candidateSummaries.has(name),
        ),
    },
    overall: metrics(baselineValues, candidateValues),
    variants: variantNames.map((variantName) => {
      const beforeSummary = baselineSummaries.get(variantName);
      const afterSummary = candidateSummaries.get(variantName);
      return {
        variant_name: variantName,
        status:
          beforeSummary && afterSummary
            ? "compared"
            : beforeSummary
              ? "removed"
              : "new",
        metrics:
          beforeSummary && afterSummary
            ? metrics(
                valuesFromSummary(beforeSummary),
                valuesFromSummary(afterSummary),
              )
            : null,
      };
    }),
  };
}

export function downloadRunComparison(
  baseline: EvaluationRunDetail,
  candidate: EvaluationRunDetail,
  format: ExportFormat,
) {
  const filename = `evalflow-comparison-${shortId(baseline.id)}-vs-${shortId(candidate.id)}.${format}`;
  if (format === "json") {
    downloadText(
      filename,
      `${JSON.stringify(comparisonExport(baseline, candidate), null, 2)}\n`,
      "application/json;charset=utf-8",
    );
    return;
  }

  const exportData = comparisonExport(baseline, candidate);
  const rows: CsvValue[][] = [
    [
      "scope",
      "variant_name",
      "metric",
      "baseline_run_id",
      "candidate_run_id",
      "baseline_dataset_id",
      "candidate_dataset_id",
      "baseline_value",
      "candidate_value",
      "delta",
      "outcome",
    ],
  ];
  runComparisonMetrics.forEach((metric) => {
    const values = exportData.overall[metric.key];
    rows.push([
      "overall",
      null,
      metric.key,
      baseline.id,
      candidate.id,
      baseline.dataset_id,
      candidate.dataset_id,
      values.baseline,
      values.candidate,
      values.delta,
      values.outcome,
    ]);
  });
  exportData.variants.forEach((variant) => {
    runComparisonMetrics.forEach((metric) => {
      const values = variant.metrics?.[metric.key];
      rows.push([
        "variant",
        variant.variant_name,
        metric.key,
        baseline.id,
        candidate.id,
        baseline.dataset_id,
        candidate.dataset_id,
        values?.baseline,
        values?.candidate,
        values?.delta,
        values?.outcome ?? variant.status,
      ]);
    });
  });
  downloadText(filename, toCsv(rows), "text/csv;charset=utf-8");
}
