"""Structured causal reasoning, in place of asking a model to be sure.

The diagnosis step used to hand a case to Gemini and take back a root cause and
a confidence number. That works, and it is unauditable: the same case can get a
different answer tomorrow, the confidence is whatever the model felt like
emitting, and there is nothing to point at when a merchant asks *why*.

This package moves the inference into a hand-encoded causal graph. The model
still reads the raw event — extracting "this failed on the 1st, with an
insufficient-funds code" from a payload is exactly what it is good at — but the
arithmetic that turns those observations into posteriors happens here, in code
somebody can read, against likelihoods somebody wrote down on purpose.

What that buys is the same answer for the same evidence, every time, with a path
through named nodes behind it.
"""

from app.agent.causal_dag.definitions import (
    DAG_VERSION,
    DAGS,
    CausalDag,
    CausalEdge,
    CausalNode,
    get_dag,
)
from app.agent.causal_dag.inference import (
    extract_observed_features,
    traverse_dag,
)

__all__ = [
    "DAGS",
    "DAG_VERSION",
    "CausalDag",
    "CausalEdge",
    "CausalNode",
    "extract_observed_features",
    "get_dag",
    "traverse_dag",
]
