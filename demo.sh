#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
SRC_DIR="$SCRIPT_DIR/src"
PIDS=()

cleanup() {
    echo ""
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

# ── Python venv ──────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install -q -r "$SRC_DIR/requirements.txt"

# ── Ollama (optional) ───────────────────────────────────────────────
MODEL_NAME="qwen2.5:0.5b"
USE_OLLAMA=false

if command -v ollama &>/dev/null; then
    echo "Ollama found — checking if $MODEL_NAME is available..."
    if ollama list 2>/dev/null | grep -q "$MODEL_NAME"; then
        echo "Model $MODEL_NAME ready."
        USE_OLLAMA=true
    else
        echo "Pulling $MODEL_NAME (this may take a minute)..."
        if ollama pull "$MODEL_NAME"; then
            USE_OLLAMA=true
        else
            echo "Pull failed — falling back to demo mode."
        fi
    fi
else
    echo "Ollama not found — running in demo mode (simulated LLM scores)."
fi

# ── Start scorer (FastAPI on :8000) ──────────────────────────────────
if $USE_OLLAMA; then
    export MODEL_ENDPOINT="http://localhost:11434/v1"
    export MODEL_NAME
    export DEMO_MODE="false"
    echo "Starting scorer in LIVE mode (Ollama)..."
else
    export DEMO_MODE="true"
    export MODEL_NAME
    echo "Starting scorer in DEMO mode..."
fi

cd "$SRC_DIR"
python3 -m uvicorn scorer:app --host 127.0.0.1 --port 8000 &
PIDS+=($!)

# Wait for scorer health
echo -n "Waiting for scorer..."
for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo " ready."
        break
    fi
    sleep 1
    echo -n "."
done

# ── Start Gradio UI (on :7860) ───────────────────────────────────────
export SCORER_URL="http://127.0.0.1:8000"
python3 -m uvicorn ui:demo --host 127.0.0.1 --port 7860 &
PIDS+=($!)

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Hybrid Fraud Detection — running"
echo ""
echo "  Scorer API:  http://127.0.0.1:8000"
echo "  Gradio UI:   http://127.0.0.1:7860"
echo "  Health:      http://127.0.0.1:8000/health"
echo ""
if $USE_OLLAMA; then
    echo "  Mode: LIVE (Ollama + $MODEL_NAME)"
else
    echo "  Mode: DEMO (simulated LLM scores)"
fi
echo "════════════════════════════════════════════════════════════"
echo "Press Ctrl+C to stop."
echo ""

wait
