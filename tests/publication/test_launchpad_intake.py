"""Publication checks required by the Launchpad Quickstart intake contract."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_validation_matrix_exposes_stage_records() -> None:
    document = yaml.safe_load((ROOT / "tests/validation_matrix.yaml").read_text())
    assert isinstance(document.get("stages"), list)
    assert document["stages"]


def test_benchmark_rubric_exposes_benchmark_records() -> None:
    document = yaml.safe_load((ROOT / "tests/benchmark_rubric.yaml").read_text())
    assert isinstance(document.get("benchmarks"), list)
    assert document["benchmarks"]


def test_showroom_contains_a_complete_hands_on_module() -> None:
    playbook = ROOT / "site.yml"
    component = ROOT / "showroom/antora.yml"
    pages = ROOT / "showroom/modules/ROOT/pages"
    assert playbook.is_file()
    assert component.is_file()

    hands_on = [
        path
        for path in sorted(pages.glob("*.adoc"))
        if path.stem not in {"index", "conclusion"}
    ]
    assert hands_on
    for path in hands_on:
        text = path.read_text()
        nonempty_lines = [line for line in text.splitlines() if line.strip()]
        assert len(nonempty_lines) >= 50
        assert "== What you will learn" in text
        assert "== See:" in text
        assert '[source,sh,role="execute"]' in text
        assert "== Verify" in text or "=== Verify" in text
        assert "== Key takeaway" in text


def test_helm_chart_exposes_the_participant_ui() -> None:
    deployment = (ROOT / "chart/templates/deployment.yaml").read_text()
    service = (ROOT / "chart/templates/service.yaml").read_text()
    route = ROOT / "chart/templates/route-ui.yaml"

    assert "name: ui" in deployment
    assert "SCORER_URL" in deployment
    assert "containerPort: 7860" in deployment
    assert "name: ui" in service
    assert "port: 7860" in service
    assert route.is_file()
    assert "targetPort: ui" in route.read_text()


def test_model_contract_is_explicit_in_default_values() -> None:
    values = yaml.safe_load((ROOT / "chart/values.yaml").read_text())
    assert values["model"]["endpoint"] == ""
    assert values["model"]["existingSecret"] == ""


def test_ci_builds_the_showroom_from_pinned_dependencies() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    workflow = (ROOT / ".github/workflows/ci.yaml").read_text()

    assert package["scripts"]["build:showroom"] == "antora --fetch site.yml"
    assert package["devDependencies"]["@antora/cli"] == "3.2.0"
    assert package["devDependencies"]["@antora/site-generator"] == "3.2.0"
    assert "npm ci" in workflow
    assert "npm run build:showroom" in workflow
