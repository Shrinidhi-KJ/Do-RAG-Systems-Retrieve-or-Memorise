"""
llm_generation.py
-----------------
Generation layer for the four-condition RAG diagnostic study.

Wraps Groq's Llama 3.1 8B. Takes a question and optional retrieved context
and returns the model's answer. This single module backs all four conditions:

    Condition A  -> generate_answer(q, context=None)           # parametric only
    Condition B  -> generate_answer(q, context=real_chunks)    # standard RAG
    Condition C  -> generate_answer(q, context=irrelevant)     # irrelevant docs
    Condition D  -> generate_answer(q, context=contradictory)  # conflicting docs

The prompt is identical across B/C/D on purpose: only the *documents* change,
so any difference in behaviour is attributable to the context, not the wording.

Requires:  pip install groq
Requires:  GROQ_API_KEY set in the environment.

Run a quick smoke test:
    python llm_generation.py
"""

import os
import time
import argparse

from groq import Groq, RateLimitError, APIError

# Verified active on Groq (Llama 3.1 8B, 128K context).
GROQ_MODEL = "llama-3.1-8b-instant"

# Temperature 0 for reproducibility — this is an experiment, not a chatbot.
# Same answer for the same input is what makes the four conditions comparable.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 512

# System prompt for GROUNDED conditions (B, C, D). Identical across all three.
# Note: this instruction tells the model to use the documents. That is the
# correct framing for measuring retrieval reliance — but it is exactly the knob
# we may want to vary in item 2 (e.g. a softer "you may use these documents"
# variant) to probe how strongly the instruction itself drives grounding.
GROUNDED_SYSTEM_PROMPT = (
    "You are a scientific question-answering assistant for offshore wind farm "
    "environmental research. Answer the question using ONLY the information in "
    "the provided documents. If the documents do not contain the answer, say so "
    "explicitly rather than guessing. Be concise and factual."
)

# System prompt for the NO-CONTEXT condition (A). No mention of documents.
PARAMETRIC_SYSTEM_PROMPT = (
    "You are a scientific question-answering assistant for offshore wind farm "
    "environmental research. Answer the question concisely and factually. "
    "If you are not sure, say so rather than guessing."
)

_client = None


def get_client():
    """Lazily build a single Groq client. Reads GROQ_API_KEY from the env."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Run setx GROQ_API_KEY \"gsk_...\" and "
                "reopen the terminal, or set it for this session."
            )
        _client = Groq(api_key=api_key)
    return _client


def build_prompt(question, context=None):
    """
    Assemble the (system_prompt, user_message) pair for one query.

    context: None              -> Condition A (no documents at all)
             list[str] or str  -> Conditions B/C/D (documents injected verbatim)
    """
    if context is None:
        return PARAMETRIC_SYSTEM_PROMPT, question

    if isinstance(context, (list, tuple)):
        # Number the chunks so the model (and you, when reading transcripts)
        # can refer to specific documents.
        joined = "\n\n".join(
            f"[Document {i + 1}]\n{chunk.strip()}" for i, chunk in enumerate(context)
        )
    else:
        joined = context.strip()

    user_message = (
        f"Documents:\n{joined}\n\n"
        f"Question: {question}\n\n"
        f"Answer based only on the documents above."
    )
    return GROUNDED_SYSTEM_PROMPT, user_message


def generate_answer(
    question,
    context=None,
    model=GROQ_MODEL,
    temperature=DEFAULT_TEMPERATURE,
    max_tokens=DEFAULT_MAX_TOKENS,
    max_retries=5,
):
    """
    Generate an answer for one question, with optional retrieved context.

    Retries with exponential backoff on rate limits (free tier is 30 req/min),
    so you can loop over your whole eval set without babysitting it.

    Returns the answer string.
    """
    system_prompt, user_message = build_prompt(question, context)
    return complete(
        system_prompt,
        user_message,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
    )


def complete(
    system_prompt,
    user_message,
    model=GROQ_MODEL,
    temperature=DEFAULT_TEMPERATURE,
    max_tokens=DEFAULT_MAX_TOKENS,
    max_retries=5,
):
    """
    Low-level single-turn chat completion with rate-limit backoff.

    Generic on purpose: the QA pipeline uses it via generate_answer(), and the
    contradiction generator (build_contradictions.py) reuses it with a different
    system prompt and a stronger editor model. One retry loop, one place to fix.

    Retries with exponential backoff on rate limits (free tier is 30 req/min),
    so you can loop over your whole eval set without babysitting it.
    """
    client = get_client()
    delay = 2.0
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError as e:
            last_err = e
            # Free tier: back off and retry. Doubles each time (2,4,8,16s...).
            time.sleep(delay)
            delay *= 2
        except APIError as e:
            # Transient server-side issues: back off, then give up after retries.
            last_err = e
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(
        f"Completion failed after {max_retries} attempts. Last error: {last_err}"
    )


def _smoke_test():
    """Run Condition A and a fake Condition B to confirm the plumbing works."""
    q = "What are the main effects of offshore wind farm noise on marine mammals?"

    print("=" * 70)
    print("CONDITION A  (no context — parametric memory)")
    print("=" * 70)
    print(generate_answer(q, context=None))

    print()
    print("=" * 70)
    print("CONDITION B-style  (with a fake context chunk)")
    print("=" * 70)
    fake_context = [
        "Pile-driving during construction of offshore wind turbines produces "
        "high-amplitude impulsive underwater noise. Studies report temporary "
        "hearing threshold shifts and avoidance behaviour in harbour porpoises "
        "within several kilometres of the source.",
    ]
    print(generate_answer(q, context=fake_context))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Groq generation layer smoke test.")
    parser.add_argument("--query", type=str, help="Ask a single question (Condition A).")
    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Optional context string to inject (makes it Condition B-style).",
    )
    args = parser.parse_args()

    if args.query:
        ctx = [args.context] if args.context else None
        print(generate_answer(args.query, context=ctx))
    else:
        _smoke_test()
