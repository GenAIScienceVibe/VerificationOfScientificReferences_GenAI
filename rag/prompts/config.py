"""
Shared configuration constants for all LLM chat-completion calls
(classifier.py, verifier.py, and any future prompt module).
"""

# SCRUM-254: temperature=0 is required on every chat-completion call so that
# the same claim + evidence always produces the same verdict. Verification
# results must be reproducible — a non-deterministic verdict would undermine
# trust in the system and make debugging/benchmarking unreliable.
LLM_TEMPERATURE: float = 0

# LLM provider for chat-completion (verifier.py only).
# We route the LLM call directly to Groq instead of OpenRouter because
# DeepInfra (one of OpenRouter's backends for this model) silently drops
# message.content on large prompts; Groq never did across 4 manual tests.
# The embedding call (embedder.py) still uses OpenRouter.
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

# LLM_MODEL = "google/gemini-2.0-flash-001"  # not available on OpenRouter
# LLM_MODEL = "meta-llama/llama-3.3-70b-instruct"  # too strict
# LLM_MODEL = "meta-llama/llama-4-scout"  # OpenRouter name (kept for reference)
LLM_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"  # Groq model ID
