from pydantic import BaseModel, Field


class DatasetItem(BaseModel):
    id: str
    input: str
    expected_output: str
    keywords: list[str] = Field(default_factory=list)


class Variant(BaseModel):
    name: str
    model: str
    provider: str = "fake"
    temperature: float = 0.0


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
    metrics: MetricScores | None
    error: str | None = None


class VariantSummary(BaseModel):
    variant_name: str
    average_exact_match: float
    average_normalized_exact_match: float
    average_keyword_score: float
    average_quality: float
    average_latency_ms: float
    error_count: int


class EvaluationReport(BaseModel):
    run_id: str
    dataset: str
    variants: list[Variant]
    summary: list[VariantSummary]
    results: list[EvaluationResult]

