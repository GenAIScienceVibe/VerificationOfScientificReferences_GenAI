# BE-13 Demo Expected Flow

This demo uses `test-data/demo/demo_text.txt` and mock RAG/GenAI mode.

Expected behavior:

1. Text document is accepted and sections are detected.
2. References are extracted, including two DOI-bearing references and one missing-DOI reference.
3. Citation-linked claims are extracted from body text only.
4. Evidence packages are created for mapped claim-reference links.
5. Cache check is safe and never reuses across different DOI values.
6. Mock RAG returns deterministic chunks from package evidence.
7. Mock GenAI verification creates validated draft results.
8. BE-11 safety rules flag weak or missing evidence for human review.
9. HTML report is generated from stored backend data.
10. Feedback and UAT survey records can be stored.

This demo validates backend orchestration and safety behavior. It does not claim final AI/RAG quality.
