# BE-4.2 Integration Note

BE-4.2 has been implemented on top of BE-4.1.

## What changed

- Improved DOI line-continuation repair.
- Prevented DOI continuation from consuming the next author name.
- Attached DOI-only and DOI URL lines to the previous reference.
- Attached journal/volume/page continuation fragments to the previous reference.
- Re-scanned final merged references for DOI values.
- Added DOI inventory and source-vs-extracted DOI coverage diagnostics.
- Added BE-4.2 quality warnings.
- Strengthened real-PDF QA script.
- Added BE-4.2 unit and real-PDF regression tests.

## What did not change

No BE-5 metadata lookup was added. No CrossRef, OpenAlex, DOI Resolver, Semantic Scholar, RAG, GenAI, claim extraction, citation mapping, evidence package, report, or feedback logic was added.
