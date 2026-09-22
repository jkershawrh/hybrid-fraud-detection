"""Helm contract for a Launchpad-issued, namespaced model runtime Secret."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELM = shutil.which("helm")
pytestmark = pytest.mark.skipif(HELM is None, reason="Helm is not installed")


def _render(*values: str) -> str:
    return subprocess.run(
        [HELM, "template", "fraud-seat", str(ROOT / "chart"), *values],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_launchpad_runtime_secret_supplies_endpoint_model_and_key():
    manifest = _render(
        "--set", "model.existingSecret=fraud-seat-runtime",
        "--set", "model.endpointFromSecret=true",
    )
    assert "name: MODEL_ENDPOINT\n              valueFrom:" in manifest
    assert "name: MODEL_NAME\n              valueFrom:" in manifest
    assert "name: MODEL_API_KEY\n              valueFrom:" in manifest
    assert "key: endpoint" in manifest
    assert "key: name" in manifest
    assert 'key: "api-key"' in manifest
    assert 'name: DEMO_MODE\n              value: "false"' in manifest


def test_secret_endpoint_mode_requires_a_secret_name():
    result = subprocess.run(
        [HELM, "template", "fraud-seat", str(ROOT / "chart"),
         "--set", "model.endpointFromSecret=true"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "model.existingSecret is required" in result.stderr


def test_default_without_endpoint_remains_explicit_simulator():
    manifest = _render()
    assert 'name: DEMO_MODE\n              value: "true"' in manifest


def test_legacy_external_endpoint_keeps_api_key_secret_compatibility():
    manifest = _render(
        "--set", "model.endpoint=https://model.example.test/v1",
        "--set", "model.name=example-model",
        "--set", "model.existingSecret=legacy-key",
    )
    assert 'name: MODEL_ENDPOINT\n              value: "https://model.example.test/v1"' in manifest
    assert 'name: MODEL_NAME\n              value: "example-model"' in manifest
    assert 'name: MODEL_API_KEY\n              valueFrom:' in manifest
    assert 'name: DEMO_MODE\n              value: "false"' in manifest
