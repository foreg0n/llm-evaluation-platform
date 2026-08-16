export type User = { id: string; email: string; is_active: boolean };

export type Project = {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type Dataset = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type DatasetItem = {
  id: string;
  dataset_id: string;
  external_id: string;
  input: string;
  expected_output: string;
  keywords: string[];
  created_at: string;
  updated_at: string;
};

export type DatasetImportResponse = {
  dataset: Dataset;
  item_count: number;
};

export type ModelVariant = {
  id: string;
  project_id: string;
  name: string;
  model: string;
  provider: string;
  temperature: number;
  max_tokens: number | null;
  system_prompt: string | null;
  timeout_seconds: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
};

export type EvaluationRun = {
  id: string;
  project_id: string;
  dataset_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  concurrency: number;
  total_tasks: number;
  completed_tasks: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  created_at: string;
};

export type EvaluationResult = {
  id: string;
  run_id: string;
  dataset_item_id: string;
  variant_id: string;
  model: string;
  provider: string;
  input: string;
  expected_output: string;
  output: string | null;
  latency_ms: number;
  metrics: Record<string, number> | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  estimated_cost: number | string | null;
  retry_count: number;
  error: string | null;
  created_at: string;
};

export type EvaluationVariantSummary = {
  variant_name: string;
  average_exact_match: number;
  average_normalized_exact_match: number;
  average_keyword_score: number;
  average_quality: number;
  average_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_estimated_cost: number | string;
  total_retries: number;
  error_count: number;
};

export type EvaluationRunDetail = EvaluationRun & {
  variant_ids: string[];
  summary: EvaluationVariantSummary[];
  results: EvaluationResult[];
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
};

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const validationMessage = Array.isArray(detail)
      ? detail
          .map((issue) => issue?.msg)
          .filter((message): message is string => typeof message === "string")
          .join("; ")
      : "";
    const message =
      typeof detail === "string"
        ? detail
        : validationMessage
          ? validationMessage
        : response.status === 401
          ? "Your session has expired. Please sign in again."
          : "The request could not be completed.";
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
