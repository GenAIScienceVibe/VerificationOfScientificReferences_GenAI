"""
Shared configuration constants for all LLM chat-completion calls
(classifier.py, verifier.py, and any future prompt module).
"""

# SCRUM-254: temperature=0 is required on every chat-completion call so that
# the same claim + evidence always produces the same verdict. Verification
# results must be reproducible — a non-deterministic verdict would undermine
# trust in the system and make debugging/benchmarking unreliable.
LLM_TEMPERATURE: float = 0
