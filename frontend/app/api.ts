export type User = {
  id: string;
  email: string;
  is_active: boolean;
  email_verified_at: string | null;
};

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
  credential_id: string | null;
  temperature: number;
  max_tokens: number | null;
  system_prompt: string | null;
  timeout_seconds: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
};

export type ProviderCatalogEntry = {
  slug: string;
  label: string;
  model_prefix: string;
  api_key_placeholder: string;
  supports_custom_base_url: boolean;
};

export type ProviderCredential = {
  id: string;
  provider: string;
  name: string;
  key_hint: string;
  api_base: string | null;
  status: "untested" | "connected" | "invalid";
  last_checked_at: string | null;
  last_used_at: string | null;
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

let activeAccessToken: string | null = null;
let accessTokenListener: ((token: string | null) => void) | null = null;
let refreshPromise: Promise<string | null> | null = null;

const NO_AUTO_REFRESH_PATHS = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/logout",
  "/api/v1/auth/refresh",
  "/api/v1/auth/register",
  "/api/v1/auth/token",
  "/api/v1/auth/email-verification/request",
  "/api/v1/auth/email-verification/confirm",
  "/api/v1/auth/password-reset/request",
  "/api/v1/auth/password-reset/confirm",
]);

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export function setApiAccessToken(token: string | null) {
  activeAccessToken = token;
  accessTokenListener?.(token);
}

export function subscribeToApiAccessToken(
  listener: (token: string | null) => void,
) {
  accessTokenListener = listener;
  return () => {
    if (accessTokenListener === listener) accessTokenListener = null;
  };
}

async function errorFromResponse(response: Response): Promise<ApiError> {
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
  return new ApiError(message, response.status);
}

export async function refreshApiAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setApiAccessToken(null);
      return null;
    }
    const payload = (await response.json()) as TokenResponse;
    setApiAccessToken(payload.access_token);
    return payload.access_token;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

async function executeApiRequest<T>(
  path: string,
  options: RequestInit,
  fallbackToken: string | undefined,
  allowRefresh: boolean,
): Promise<T> {
  const token = activeAccessToken ?? fallbackToken;
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (
    response.status === 401 &&
    allowRefresh &&
    token &&
    !NO_AUTO_REFRESH_PATHS.has(path)
  ) {
    const refreshedToken = await refreshApiAccessToken();
    if (refreshedToken) {
      return executeApiRequest<T>(path, options, refreshedToken, false);
    }
  }
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  return executeApiRequest<T>(path, options, token, true);
}
