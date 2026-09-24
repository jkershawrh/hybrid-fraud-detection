"""Publication checks required by the Launchpad Quickstart intake contract."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


def test_base_and_smoke_images_are_immutable() -> None:
    hook = yaml.safe_load((ROOT / "chart/templates/test-scorer.yaml").read_text())
    containerfile = (ROOT / "src/Containerfile").read_text().splitlines()
    base_image = next(line.removeprefix("FROM ") for line in containerfile if line.startswith("FROM "))

    assert IMMUTABLE_IMAGE.fullmatch(hook["spec"]["containers"][0]["image"])
    assert IMMUTABLE_IMAGE.fullmatch(base_image)


def test_candidate_publisher_is_manual_scoped_and_signed() -> None:
    workflow = (ROOT / ".github/workflows/ci.yaml").read_text()
    document = yaml.safe_load(workflow)
    triggers = document.get("on", document.get(True))
    assert triggers["workflow_dispatch"]["inputs"]["publish_candidate"]["default"] is False
    job = document["jobs"]["publish_candidate"]
    assert job["environment"] == "intake-candidate-publish"
    assert "inputs.publish_candidate == true" in job["if"]
    assert "refs/heads/codex/hybrid-fraud-immutable-images" in job["if"]
    assert set(job["needs"]) == set(document["jobs"]) - {"publish_candidate"}
    assert job["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    assert "QUAY_ROBOT_USERNAME" not in workflow
    assert "QUAY_ROBOT_TOKEN" not in workflow
    assert "secrets.GITHUB_TOKEN" in workflow
    assert "vars.CANDIDATE_PUBLISH_ENABLED" in workflow
    assert "EXPECTED_REVISION" in workflow
    assert "GITHUB_SHA" in workflow
    assert "cosign sign --yes" in workflow
    assert "cosign attest --yes" in workflow
    assert "cosign verify-attestation" in workflow
    assert "anchore/sbom-action@" in workflow
    assert "--digestfile" in workflow
    assert "ghcr.io/jkershawrh/hybrid-fraud-detection" in workflow


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


def test_showroom_delivers_the_full_decision_journey() -> None:
    pages = ROOT / "showroom/modules/ROOT/pages"
    nav = (ROOT / "showroom/modules/ROOT/nav.adoc").read_text()
    journey = [
        "01-hybrid-scoring.adoc",
        "02-rule-evidence.adoc",
        "03-conditional-inference.adoc",
        "04-portfolio-observability.adoc",
        "05-challenge-and-govern.adoc",
    ]

    for page in journey:
        assert (pages / page).is_file()
        assert page in nav

    total_words = sum(len(path.read_text().split()) for path in pages.glob("*.adoc"))
    assert total_words >= 4500

    images = ROOT / "showroom/modules/ROOT/assets/images"
    assert {path.name for path in images.glob("*.svg")} >= {
        "hybrid-architecture.svg",
        "decision-flow.svg",
        "governance-layers.svg",
    }


def test_showroom_owns_and_explains_the_workspace_contract() -> None:
    config = yaml.safe_load((ROOT / "ui-config.yml").read_text())
    assert [tab["name"] for tab in config["tabs"]] == [
        "Hybrid Decision Casebook",
        "Terminal",
        "OpenShift Console",
    ]
    content = "\n".join(
        path.read_text() for path in (ROOT / "showroom/modules/ROOT/pages").glob("*.adoc")
    )
    assert content.count("Hybrid Decision Casebook") >= 7
    ui = (ROOT / "src/ui.py").read_text()
    for stage in ("calculate rule evidence", "route ambiguity", "compare a portfolio", "challenge and govern"):
        assert stage in ui


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
