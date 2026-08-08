from pydantic import BaseModel, Field


class DatasetItem(BaseModel):
    id: str
    input: str
    expected_output: str
    keywords: list[str] = Field(default_factory=list)


class Variant(BaseModel):
    name: str
    model: str
    provider: str = "litellm"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=500, gt=0)
    system_prompt: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)


class GenerationResponse(BaseModel):
    output: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    retry_count: int = 0


class MetricScores(BaseModel):
    exact_match: float
    normalized_exact_match: float
    keyword_score: float

    @property
    def quality(self) -> float:
        return (
            self.exact_match
            + self.normalized_exact_match
            + self.keyword_score
        ) / 3


class EvaluationResult(BaseModel):
    item_id: str
    variant_name: str
    model: str
    provider: str
    input: str
    expected_output: str
    output: str | None
    latency_ms: float
    metrics: MetricScores | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    retry_count: int = 0
    error: str | None = None


class VariantSummary(BaseModel):
    variant_name: str
    average_exact_match: float
    average_normalized_exact_match: float
    average_keyword_score: float
    average_quality: float
    average_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_estimated_cost: float
    total_retries: int
    error_count: int


class EvaluationReport(BaseModel):
    run_id: str
    dataset: str
    variants: list[Variant]
    summary: list[VariantSummary]
    results: list[EvaluationResult]

