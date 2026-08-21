"""Gradio UI for hybrid fraud detection scoring.

Provides three tabs:
  1. Score Transaction -- single transaction form with pre-filled example
  2. Batch Analysis   -- JSON array input for bulk scoring
  3. Statistics        -- cumulative scoring metrics
"""

import json
import os

import gradio as gr
import httpx

SCORER_URL = os.environ.get("SCORER_URL", "http://localhost:8000")

COUNTRIES = ["US", "UK", "NG", "KY", "CH"]
COUNTRY_LABELS = {
    "US": "US",
    "UK": "UK",
    "NG": "Nigeria",
    "KY": "Cayman Islands",
    "CH": "Switzerland",
}
CATEGORIES = ["retail", "wire_transfer", "crypto", "investment"]

RISK_COLORS = {
    "low": "#22c55e",
    "medium": "#eab308",
    "high": "#f97316",
    "critical": "#ef4444",
}

DISCLAIMER = (
    "Rule-based signals are deterministic. "
    "LLM risk assessment is AI-generated; this educational demo is not for real decisions."
)


def _post(path: str, payload: dict) -> dict:
    """POST to the scorer backend and return JSON."""
    resp = httpx.post(f"{SCORER_URL}{path}", json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _get(path: str) -> dict:
    """GET from the scorer backend and return JSON."""
    resp = httpx.get(f"{SCORER_URL}{path}", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _risk_badge(level: str) -> str:
    color = RISK_COLORS.get(level, "#6b7280")
    return (
        f'<span style="background:{color};color:white;padding:4px 12px;'
        f'border-radius:6px;font-weight:bold;font-size:1.1em;">'
        f"{level.upper()}</span>"
    )


def score_transaction(amount: float, country: str, category: str, description: str) -> str:
    """Score a single transaction and format the result as HTML."""
    try:
        result = _post("/api/v1/score", {
            "amount": amount,
            "currency": "USD",
            "country": country,
            "category": category,
            "description": description,
        })
    except Exception as e:
        return f"<p style='color:red;'>Error contacting scorer: {e}</p>"

    signals_html = "".join(
        f"<li><b>{s['signal']}</b> (+{s['weight']}): {s['detail']}</li>"
        for s in result.get("signals", [])
    )

    llm_display = (
        f"{result['llm_score']:.1f}"
        if result.get("llm_score") is not None
        else "skipped"
    )

    skip_info = ""
    if result.get("llm_skipped"):
        reason = result.get("skip_reason", "")
        skip_info = f"<p><em>LLM skipped: {reason}</em></p>"

    return f"""
    <div style="font-family:sans-serif;">
      <p>Risk Level: {_risk_badge(result['risk_level'])}</p>
      <table style="border-collapse:collapse;margin:8px 0;">
        <tr><td style="padding:4px 12px;"><b>Final Score</b></td>
            <td style="padding:4px 12px;">{result['risk_score']:.1f}</td></tr>
        <tr><td style="padding:4px 12px;"><b>Rule Score</b></td>
            <td style="padding:4px 12px;">{result['rule_score']:.1f}</td></tr>
        <tr><td style="padding:4px 12px;"><b>LLM Score</b></td>
            <td style="padding:4px 12px;">{llm_display}</td></tr>
        <tr><td style="padding:4px 12px;"><b>Latency</b></td>
            <td style="padding:4px 12px;">{result['latency_ms']:.1f} ms</td></tr>
        <tr><td style="padding:4px 12px;"><b>Scorer</b></td>
            <td style="padding:4px 12px;">{result['model']}</td></tr>
      </table>
      {skip_info}
      <p><b>Detected Signals:</b></p>
      <ul>{signals_html if signals_html else '<li>None</li>'}</ul>
    </div>
    """


def score_batch(json_text: str) -> str:
    """Score a batch of transactions from JSON input."""
    try:
        transactions = json.loads(json_text)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    if not isinstance(transactions, list):
        return "Input must be a JSON array of transaction objects."

    try:
        result = _post("/api/v1/batch", {"transactions": transactions})
    except Exception as e:
        return f"Error contacting scorer: {e}"

    rows = []
    for i, r in enumerate(result.get("results", [])):
        llm = f"{r['llm_score']:.1f}" if r.get("llm_score") is not None else "skipped"
        rows.append(
            f"| {i+1} | {r['risk_level']} | {r['risk_score']:.1f} "
            f"| {r['rule_score']:.1f} | {llm} | {r['latency_ms']:.1f} ms |"
        )

    header = "| # | Risk Level | Final | Rule | LLM | Latency |\n|---|---|---|---|---|---|"
    table = header + "\n" + "\n".join(rows)
    summary = f"\n\n**Total:** {result['total']} | **Avg Latency:** {result['avg_latency_ms']:.1f} ms"
    return table + summary


def get_stats() -> str:
    """Fetch and format scoring statistics."""
    try:
        stats = _get("/api/v1/stats")
    except Exception as e:
        return f"Error fetching stats: {e}"

    return (
        f"**Total Scored:** {stats['total_scored']}\n\n"
        f"**Avg Latency:** {stats['avg_latency_ms']:.1f} ms\n\n"
        f"**LLM Skip Rate:** {stats['llm_skip_rate_pct']:.1f}%\n\n"
        f"**LLM Calls:** {stats['llm_calls']}\n\n"
        f"**LLM Skips:** {stats['llm_skips']}\n\n"
        f"**LLM Failures:** {stats['llm_failures']}\n\n"
        f"**Mode:** {stats['mode']}"
    )


# ---------------------------------------------------------------------------
# Gradio Blocks interface
# ---------------------------------------------------------------------------

EXAMPLE_BATCH = json.dumps([
    {"amount": 15000, "country": "NG", "category": "wire_transfer", "description": "Overseas payment"},
    {"amount": 50, "country": "US", "category": "retail", "description": "Coffee shop"},
    {"amount": 9999, "country": "KY", "category": "crypto", "description": "BTC purchase"},
], indent=2)

with gr.Blocks(title="Hybrid Fraud Detection") as demo:
    gr.Markdown("# Fraud Detection Dashboard")
    gr.Markdown(
        "Explore hybrid transaction scoring with visible example rules and model output."
    )

    with gr.Tab("Score Transaction"):
        with gr.Row():
            with gr.Column():
                amount = gr.Number(label="Amount ($)", value=15000)
                country = gr.Dropdown(
                    label="Country",
                    choices=[(COUNTRY_LABELS[c], c) for c in COUNTRIES],
                    value="NG",
                )
                category = gr.Dropdown(
                    label="Category",
                    choices=CATEGORIES,
                    value="wire_transfer",
                )
                description = gr.Textbox(
                    label="Description",
                    value="Overseas wire transfer to Nigeria",
                )
                score_btn = gr.Button("Score Transaction", variant="primary")
            with gr.Column():
                output = gr.HTML(label="Result")
        gr.Markdown(f"*{DISCLAIMER}*")
        score_btn.click(
            fn=score_transaction,
            inputs=[amount, country, category, description],
            outputs=output,
        )

    with gr.Tab("Batch Analysis"):
        batch_input = gr.Textbox(
            label="Transactions (JSON array)",
            lines=10,
            value=EXAMPLE_BATCH,
        )
        batch_btn = gr.Button("Score Batch", variant="primary")
        batch_output = gr.Markdown(label="Results")
        batch_btn.click(fn=score_batch, inputs=batch_input, outputs=batch_output)

    with gr.Tab("Statistics"):
        stats_btn = gr.Button("Refresh Statistics", variant="secondary")
        stats_output = gr.Markdown(label="Stats")
        stats_btn.click(fn=get_stats, outputs=stats_output)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
