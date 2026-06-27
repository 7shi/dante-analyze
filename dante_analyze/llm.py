"""LLM call boundary: the `call_llm` runaway-guarded wrapper, `step_sep` progress
separator, and the MAX_LENGTH / LLM_RETRIES constants that parameterize it."""
import sys
from llm7shi import Client

MAX_LENGTH = 10000   # cap one generate reply (chars); pins a model that runs away
LLM_RETRIES = 3      # regenerate this many times if a reply shows repetition / hits MAX_LENGTH


def step_sep(title):
    print(f"\n--- {title} ---")


def call_llm(messages, model, retries=LLM_RETRIES, max_length=MAX_LENGTH,
             include_thoughts=False):
    """generate_with_schema wrapper guarding a local model that runs away in free
    text: cap the reply and, on repetition or hitting the cap, REGENERATE (runaway
    is stochastic, so a fresh draw usually recovers). Returns the first clean
    Response, or the last one after `retries`.

    Chain-of-thought is OFF by default — for the checkable passes (digest) deliberation
    gets its own plain-text turn instead. `include_thoughts=True`
    turns it on for the UNCHECKABLE reading pass, where precision matters more than
    speed and there is no structured output for CoT to corrupt (the thinking stays
    internal; `resp.text` is still the clean prose). Maps to ollama `think=`, which
    gracefully falls back to off if the model has no thinking capability."""
    if not messages:
        raise ValueError("messages list cannot be empty")

    history = messages.copy()
    last_msg = history.pop()
    prompt = last_msg["content"]

    # Instantiate LLM client wrapping the quality retry logic
    client = Client(
        model=model,
        include_thoughts=include_thoughts,
        file=sys.stderr,
        show_params=False,
        max_length=max_length,
        retries=retries
    )

    # Move system prompt to client's dedicated system prompt handler
    if history and history[0].get("role") == "system":
        client.set_system_prompt(history[0]["content"])
        history.pop(0)

    client.history = history

    # Direct function invocation triggers __call__ and quality retries
    return client(prompt)
