"""Hybrid Fraud Detection Scorer.

Combines a deterministic rule engine with LLM risk assessment for
explainable, auditable fraud scoring. Runs on Intel Xeon CPU.

Conditional pipeline: if the rule engine is confident (score > 90 or < 10),
the LLM call is skipped entirely, reducing latency and compute cost.

Combined score = 60% rule + 40% LLM (when LLM is invoked).
"""

import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_ENDPOINT = os.environ.get("MODEL_ENDPOINT", "")
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen2.5:0.5b")
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("true", "1", "yes")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("fraud-scorer")

AI_DISCLAIMER = (
    "Rule-based signals are deterministic. "
    "LLM risk assessment is AI-generated -- verify critical decisions."
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIGH_RISK_COUNTRIES = {
    "NG", "RU", "KP", "IR", "SY", "MM", "VE", "AF", "IQ", "LY",
}

HIGH_RISK_CATEGORIES = {
    "wire_transfer", "crypto", "gambling", "money_order", "prepaid_card",
}

# Confidence thresholds for conditional LLM skip
SKIP_HIGH_THRESHOLD = 90  # rule_score above this -> skip LLM (confident high)
SKIP_LOW_THRESHOLD = 10   # rule_score below this -> skip LLM (confident low)

# Combination weights
RULE_WEIGHT = 0.6
LLM_WEIGHT = 0.4

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TransactionRequest(BaseModel):
    amount: float
    currency: str = "USD"
    country: str = "US"
    category: str = "retail"
    description: str = ""


class Signal(BaseModel):
    signal: str
    weight: int
    detail: str


class ScoreResponse(BaseModel):
    risk_level: str
    risk_score: float
    rule_score: float
    llm_score: Optional[float] = None
    signals: list[Signal]
    llm_skipped: bool
    skip_reason: Optional[str] = None
    latency_ms: float
    model: str
    ai_disclaimer: str


class BatchRequest(BaseModel):
    transactions: list[TransactionRequest]


class BatchResponse(BaseModel):
    results: list[ScoreResponse]
    total: int
    avg_latency_ms: float


class StatsResponse(BaseModel):
    total_scored: int
    avg_latency_ms: float
    llm_skip_rate_pct: float
    llm_calls: int
    llm_skips: int
    mode: str


# ---------------------------------------------------------------------------
# Rule Engine
# ---------------------------------------------------------------------------


class RuleEngine:
    """Deterministic signal detection for fraud scoring.

    Produces a 0-100 rule score based on transaction attributes.
    Each detected signal adds a fixed weight to a base score of 10.
    """

    BASE_SCORE = 10.0

    def score(self, tx: TransactionRequest) -> tuple[float, list[Signal]]:
        """Return (rule_score, signals) for a transaction."""
        signals: list[Signal] = []
        score = self.BASE_SCORE

        # High amount: > $10K
        if tx.amount > 10_000:
            signals.append(Signal(
                signal="high_amount",
                weight=30,
                detail=f"${tx.amount:,.0f} exceeds $10K threshold",
            ))
            score += 30

        # High-risk country
        if tx.country.upper() in HIGH_RISK_COUNTRIES:
            signals.append(Signal(
                signal="high_risk_country",
                weight=25,
                detail=f"{tx.country.upper()} is a high-risk jurisdiction",
            ))
            score += 25

        # High-risk category
        if tx.category.lower() in HIGH_RISK_CATEGORIES:
            signals.append(Signal(
                signal="high_risk_category",
                weight=15,
                detail=f"{tx.category} is a high-risk transaction type",
            ))
            score += 15

        # Round amount (structuring indicator)
        if tx.amount > 0 and tx.amount % 1000 == 0:
            signals.append(Signal(
                signal="round_amount",
                weight=5,
                detail="Exact round number -- possible structuring",
            ))
            score += 5

        # Crypto transaction
        if tx.category.lower() == "crypto":
            signals.append(Signal(
                signal="crypto_transaction",
                weight=10,
                detail="Cryptocurrency transaction detected",
            ))
            score += 10

        return min(score, 100.0), signals


# ---------------------------------------------------------------------------
# LLM Scorer
# ---------------------------------------------------------------------------


class LLMScorer:
    """Calls an LLM endpoint for risk assessment, extracting a 0-100 score."""

    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=30.0)

    def score(self, tx: TransactionRequest, signals: list[Signal]) -> tuple[float, float]:
        """Return (llm_score, latency_ms). Raises on failure."""
        prompt = (
            "Assess the fraud risk of this transaction on a scale of 0-100. "
            "0 = no risk, 100 = certain fraud. Consider amount, country, and category. "
            "Respond with ONLY a number.\n\n"
            f"Amount: ${tx.amount:,.2f}\n"
            f"Country: {tx.country}\n"
            f"Category: {tx.category}\n"
            f"Signals detected: {len(signals)}"
        )

        start = time.monotonic()
        response = self.client.post(
            f"{self.endpoint}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 16,
            },
        )
        latency_ms = (time.monotonic() - start) * 1000
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Extract numeric score from response
        cleaned = "".join(c for c in content if c.isdigit() or c == ".")
        if not cleaned:
            raise ValueError(f"LLM returned non-numeric response: {content}")
        llm_score = min(float(cleaned), 100.0)
        return llm_score, latency_ms


class DemoLLMScorer:
    """Simulated LLM scorer for demo mode (no backend required)."""

    def __init__(self, model: str):
        self.model = model

    def score(self, tx: TransactionRequest, signals: list[Signal]) -> tuple[float, float]:
        """Return a simulated score based on signals, with artificial latency."""
        # Simulate a plausible LLM score: correlated with rule signals but noisy
        base = len(signals) * 15.0
        noise = random.uniform(-10, 10)
        llm_score = max(0.0, min(100.0, base + noise + 10))
        # Simulate inference latency
        latency_ms = random.uniform(50, 200)
        return llm_score, latency_ms


# ---------------------------------------------------------------------------
# Hybrid Scorer
# ---------------------------------------------------------------------------


@dataclass
class ScoringStats:
    """Tracks cumulative scoring statistics."""
    total_scored: int = 0
    total_latency_ms: float = 0.0
    llm_calls: int = 0
    llm_skips: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_scored == 0:
            return 0.0
        return self.total_latency_ms / self.total_scored

    @property
    def llm_skip_rate_pct(self) -> float:
        if self.total_scored == 0:
            return 0.0
        return (self.llm_skips / self.total_scored) * 100.0


class HybridScorer:
    """Combines rule engine (60%) with LLM scoring (40%).

    Conditional pipeline: skips LLM when rule engine is confident
    (score > 90 or score < 10), saving latency and compute.
    """

    def __init__(self, rule_engine: RuleEngine, llm_scorer, model_name: str):
        self.rule_engine = rule_engine
        self.llm_scorer = llm_scorer
        self.model_name = model_name
        self.stats = ScoringStats()

    def score(self, tx: TransactionRequest) -> ScoreResponse:
        start = time.monotonic()

        # Step 1: Rule engine (always runs)
        rule_score, signals = self.rule_engine.score(tx)

        # Step 2: Conditional LLM scoring
        llm_score: Optional[float] = None
        llm_skipped = False
        skip_reason: Optional[str] = None

        if rule_score > SKIP_HIGH_THRESHOLD:
            llm_skipped = True
            skip_reason = f"Rule score {rule_score:.0f} > {SKIP_HIGH_THRESHOLD} -- rule engine confident (high risk)"
            combined_score = rule_score
            self.stats.llm_skips += 1
        elif rule_score < SKIP_LOW_THRESHOLD:
            llm_skipped = True
            skip_reason = f"Rule score {rule_score:.0f} < {SKIP_LOW_THRESHOLD} -- rule engine confident (low risk)"
            combined_score = rule_score
            self.stats.llm_skips += 1
        else:
            # Ambiguous: call LLM for additional assessment
            try:
                llm_score, _llm_latency = self.llm_scorer.score(tx, signals)
                combined_score = (rule_score * RULE_WEIGHT) + (llm_score * LLM_WEIGHT)
                self.stats.llm_calls += 1
            except Exception as e:
                logger.warning("LLM scoring failed, using rule score only: %s", e)
                combined_score = rule_score
                llm_skipped = True
                skip_reason = f"LLM call failed: {e}"
                self.stats.llm_skips += 1

        combined_score = min(combined_score, 100.0)
        latency_ms = (time.monotonic() - start) * 1000

        # Determine risk level
        if combined_score >= 80:
            risk_level = "critical"
        elif combined_score >= 60:
            risk_level = "high"
        elif combined_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Update stats
        self.stats.total_scored += 1
        self.stats.total_latency_ms += latency_ms

        return ScoreResponse(
            risk_level=risk_level,
            risk_score=round(combined_score, 2),
            rule_score=round(rule_score, 2),
            llm_score=round(llm_score, 2) if llm_score is not None else None,
            signals=signals,
            llm_skipped=llm_skipped,
            skip_reason=skip_reason,
            latency_ms=round(latency_ms, 2),
            model=self.model_name if not llm_skipped else "rule-engine-only",
            ai_disclaimer=AI_DISCLAIMER,
        )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fraud Detection API",
    description="AI-powered transaction screening with explainable risk scoring",
    version="1.0.0",
)

# Initialize scorer
rule_engine = RuleEngine()

if DEMO_MODE or not MODEL_ENDPOINT:
    if not MODEL_ENDPOINT:
        logger.info("Starting in DEMO mode (no MODEL_ENDPOINT configured)")
    else:
        logger.info("Starting in DEMO mode (DEMO_MODE=true)")
    llm_scorer = DemoLLMScorer(model=MODEL_NAME)
    _active_mode = "demo"
else:
    # Attempt to verify Ollama connectivity; fall back to demo if unreachable
    try:
        _probe = httpx.get(f"{MODEL_ENDPOINT.rstrip('/')}/models", timeout=5.0)
        _probe.raise_for_status()
        logger.info("Starting in LIVE mode with endpoint: %s", MODEL_ENDPOINT)
        llm_scorer = LLMScorer(endpoint=MODEL_ENDPOINT.rstrip("/").removesuffix("/v1"), model=MODEL_NAME)
        _active_mode = "live"
    except Exception as e:
        logger.warning(
            "Ollama endpoint not reachable (%s), falling back to demo mode. "
            "The scorer will retry on each request if MODEL_ENDPOINT is set.",
            e,
        )
        llm_scorer = DemoLLMScorer(model=MODEL_NAME)
        _active_mode = "demo"

hybrid_scorer = HybridScorer(
    rule_engine=rule_engine,
    llm_scorer=llm_scorer,
    model_name=MODEL_NAME,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": _active_mode,
        "model": MODEL_NAME,
    }


@app.post("/api/v1/score", response_model=ScoreResponse)
def score_transaction(tx: TransactionRequest):
    return hybrid_scorer.score(tx)


@app.post("/api/v1/batch", response_model=BatchResponse)
def batch_score(batch: BatchRequest):
    results = [hybrid_scorer.score(tx) for tx in batch.transactions]
    total_latency = sum(r.latency_ms for r in results)
    avg_latency = total_latency / len(results) if results else 0.0
    return BatchResponse(
        results=results,
        total=len(results),
        avg_latency_ms=round(avg_latency, 2),
    )


@app.get("/api/v1/stats", response_model=StatsResponse)
def get_stats():
    stats = hybrid_scorer.stats
    return StatsResponse(
        total_scored=stats.total_scored,
        avg_latency_ms=round(stats.avg_latency_ms, 2),
        llm_skip_rate_pct=round(stats.llm_skip_rate_pct, 2),
        llm_calls=stats.llm_calls,
        llm_skips=stats.llm_skips,
        mode=_active_mode,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
