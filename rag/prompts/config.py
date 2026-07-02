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
# We route directly to Groq — lower latency and no null-content drops.
# The embedding call (embedder.py) uses OpenRouter.
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"  # kept for embedder.py

# LLM_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"  # not on Groq or OpenRouter (access denied)
# LLM_MODEL = "meta-llama/llama-3.3-70b-versatile"             # llama-3.3 70B on Groq
LLM_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"  # scout on Groq: previously working
