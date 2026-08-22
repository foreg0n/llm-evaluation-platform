import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY = ROOT / "observability"
DASHBOARD_PATH = (
    OBSERVABILITY / "grafana" / "dashboards" / "evalflow-overview.json"
)
DATASOURCE_PATH = (
    OBSERVABILITY
    / "grafana"
    / "provisioning"
    / "datasources"
    / "prometheus.yml"
)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_observability_compose_uses_pinned_local_services() -> None:
    compose = load_yaml(ROOT / "compose.observability.yaml")
    services = compose["services"]

    assert services["prometheus"]["image"] == "prom/prometheus:v3.13.1"
    assert services["grafana"]["image"] == "grafana/grafana:13.1.3"
    assert services["prometheus"]["ports"] == [
        "127.0.0.1:${PROMETHEUS_PORT:-9090}:9090"
    ]
    assert services["grafana"]["ports"] == [
        "127.0.0.1:${GRAFANA_PORT:-3001}:3000"
    ]
    assert "host.docker.internal:host-gateway" in services["prometheus"][
        "extra_hosts"
    ]


def test_prometheus_scrapes_api_worker_and_loads_rules() -> None:
    config = load_yaml(OBSERVABILITY / "prometheus" / "prometheus.yml")
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}

    assert set(jobs) == {"prometheus", "evalflow-api", "evalflow-worker"}
    assert jobs["evalflow-api"]["static_configs"][0]["targets"] == [
        "host.docker.internal:8000"
    ]
    assert jobs["evalflow-worker"]["static_configs"][0]["targets"] == [
        "host.docker.internal:9808"
    ]
    assert config["rule_files"] == ["/etc/prometheus/rules/*.yml"]


def test_alert_rules_cover_availability_errors_latency_and_failures() -> None:
    rules = load_yaml(OBSERVABILITY / "prometheus" / "alerts.yml")
    alerts = [rule for group in rules["groups"] for rule in group["rules"]]
    names = {rule["alert"] for rule in alerts}

    assert len(alerts) == 7
    assert len(names) == len(alerts)
    assert {
        "EvalflowApiDown",
        "EvalflowWorkerDown",
        "EvalflowReadinessFailure",
        "EvalflowHighHttpErrorRate",
        "EvalflowHighHttpLatency",
        "EvalflowEvaluationRunFailed",
        "EvalflowCeleryTaskFailed",
    } == names
    assert all(rule.get("expr") for rule in alerts)
    assert all(rule.get("for") for rule in alerts)
    assert all(rule.get("labels", {}).get("severity") for rule in alerts)


def test_grafana_dashboard_matches_provisioned_datasource() -> None:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    datasource = load_yaml(DATASOURCE_PATH)["datasources"][0]
    panels = dashboard["panels"]

    assert dashboard["uid"] == "evalflow-overview"
    assert datasource["uid"] == "evalflow-prometheus"
    assert datasource["url"] == "http://prometheus:9090"
    assert len(panels) >= 10
    assert len({panel["id"] for panel in panels}) == len(panels)
    assert len({panel["title"] for panel in panels}) == len(panels)
    assert all(
        panel.get("datasource", {}).get("uid") == datasource["uid"]
        for panel in panels
    )

    expressions = [
        target["expr"]
        for panel in panels
        for target in panel.get("targets", [])
        if "expr" in target
    ]
    assert expressions
    assert all("evalflow_" in expr or "up{" in expr for expr in expressions)
    assert all("/api/v1/runs/" not in expr for expr in expressions)
