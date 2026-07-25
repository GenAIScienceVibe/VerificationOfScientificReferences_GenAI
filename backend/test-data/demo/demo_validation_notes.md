# BE-13 Demo Validation Notes

Use this when presenting the backend:

```bash
python scripts/reset_demo_db.py
python scripts/run_demo_pipeline.py
```

Then open Swagger at `http://127.0.0.1:8000/docs` and inspect:

- document summary
- verification results
- safety checks
- generated report
- feedback and UAT endpoints

Mock mode indicators are configured in `.env.example`. Mock mode is deterministic and presentation-safe, but it is not a substitute for real RAG/GenAI quality validation.
