import { useState, useEffect } from 'react'

function HowItWorksPage() {
  const [activeTab, setActiveTab] = useState('general')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const tab = params.get('tab')
    if (tab) setActiveTab(tab)

    const hash = window.location.hash
    if (hash) {
      setTimeout(() => {
        const el = document.querySelector(hash)
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 100)
    }
  }, [])

  const generalSteps = [
    {
      step: 1,
      title: "PDF Upload & Parsing",
      description: "You upload a research paper as a PDF. verifAi extracts the full text of the document, identifies individual claims, and detects all in-text citations (e.g. [Author et al., 2019]) along with the corresponding reference list at the end of the paper.",
      detail: "Technology: PDF text extraction, citation pattern recognition via regular expressions and NLP."
    },
    {
      step: 2,
      title: "Reference Retrieval",
      description: "For each citation, verifAi attempts to retrieve the original source. It uses the DOI (Digital Object Identifier) or metadata (author, year, title) to look up the actual paper via academic APIs such as Crossref, Semantic Scholar, or PubMed.",
      detail: "Technology: DOI resolution, academic database APIs, metadata matching."
    },
    {
      step: 3,
      title: "Claim Extraction & Matching",
      description: "Each claim in the paper is extracted and paired with its cited source. A large language model (LLM) then reads both the claim and the relevant passage from the cited paper, and determines whether the claim is accurately supported.",
      detail: "Technology: LLM-based reading comprehension, RAG (Retrieval-Augmented Generation), semantic similarity."
    },
    {
      step: 4,
      title: "Verification & Report",
      description: "Each claim receives a verdict: Supported, Partially Supported, Unsupported, or Hallucinated (source doesn't exist). A credibility score is calculated based on the overall results. You can view AI reasoning for each claim and export the full report as a PDF.",
      detail: "Technology: Classification model, confidence scoring, jsPDF report generation."
    },
  ]

  const technicalSteps = [
    {
      step: 1,
      title: "Document Processing Pipeline",
      points: [
        "Document text is extracted with PyMuPDF. Reference list detection uses heading pattern recognition (e.g. 'References', 'Bibliography') with a sentence-segmentation fallback when no clear section is found - currently targets English-language heading conventions.",
        "Each pipeline stage (text extraction → reference extraction → DOI/metadata resolution → claim extraction → evidence retrieval → GenAI verification → safety policy gating) persists intermediate results to a relational store, making the pipeline resumable and individually inspectable per document.",
      ],
    },
    {
      step: 2,
      title: "Reference Resolution",
      points: [
        "DOI extraction first looks for explicit DOI strings in each reference entry. If none is found, a title-based fallback queries CrossRef → OpenAlex → Semantic Scholar → CORE in sequence, with each candidate validated against three guards: title similarity ≥ 0.95, publication year agreement within ±1, and at least one matching author surname.",
        "Special-cased identifier formats are handled explicitly: arXiv preprints (DOI prefix 10.48550/arXiv.*) resolve via Semantic Scholar + the arXiv PDF endpoint; SSRN working papers (10.2139/ssrn.*) are flagged as a distinct preprint evidence tier with a capped confidence ceiling and mandatory human review.",
        "Once a source is resolved, verifAi attempts full-text retrieval via Unpaywall (legal open-access PDF discovery) and CORE (full-text API fallback) before falling back to abstract-only evidence. Some publishers report open-access status without exposing a programmatically retrievable PDF; in these cases users can upload the source PDF manually to enable full re-verification.",
      ],
    },
    {
      step: 3,
      title: "Evidence Retrieval & Verification (RAG + LLM)",
      points: [
        "Retrieved text is chunked and embedded (OpenAI-compatible embedding model, accessed via OpenRouter), and the resulting vectors are indexed for similarity search against the claim text using cosine similarity.",
        "A configurable similarity threshold (currently 0.50) determines whether retrieved evidence is considered strong enough to support a verdict; scores below this threshold are flagged as insufficient evidence rather than treated as a negative result.",
        "A language model receives the claim and its retrieved evidence and produces a structured verdict (Supported / Partially Supported / Not Supported) with a written justification, rather than a single opaque confidence number.",
      ],
    },
    {
      step: 4,
      title: "Safety Policy & Reporting",
      points: [
        "A deterministic safety policy layer sits on top of the LLM output and can override or cap its verdict based on independently-checked conditions: DOI validity, evidence availability tier, and similarity score.",
        "Claims with an invalid or unresolvable DOI are treated as a strong fabrication signal. Claims where a malformed model response is encountered are routed to a conservative human-review state rather than silently defaulting to a verdict.",
        "The final credibility score and PDF report are generated client-side via jsPDF.",
      ],
    },
  ]

  const categories = [
    {
      color: "#16a34a", bg: "#f0fdf4", border: "#86efac",
      label: "Supported",
      anchor: "supported",
      meaning: "The AI found relevant text in the cited source that clearly and directly confirms the claim as stated.",
      conditions: [
        "A valid DOI was resolved and full text (or a sufficient abstract) was retrieved.",
        "The similarity score between the claim embedding and the best retrieved chunk is ≥ 0.50.",
        "The language model judged the claim to be accurately reflected in the source.",
        "No safety rules overrode the verdict (e.g. no invalid DOI, no source-unavailable flag).",
      ],
      note: null,
    },
    {
      color: "#d97706", bg: "#fffbeb", border: "#fcd34d",
      label: "Partially Supported",
      anchor: "partially-supported",
      meaning: "The cited source addresses the same topic or contains related evidence, but does not fully confirm all aspects of the claim — for example, the numbers differ, the scope is narrower, or the framing adds unstated qualifications.",
      conditions: [
        "Same retrieval requirements as Supported (valid DOI, sufficient similarity score).",
        "The language model found relevant evidence but judged it to only partially match the claim.",
        "Common causes: paraphrasing that overstates the original finding, missing caveats, or a claim that combines two separate results into one.",
      ],
      note: null,
    },
    {
      color: "#dc2626", bg: "#fef2f2", border: "#fca5a5",
      label: "Unsupported",
      anchor: "unsupported",
      meaning: "The cited source was successfully retrieved and read, but the AI found that the claim contradicts or is not present in the source content.",
      conditions: [
        "Valid DOI resolved, full text or abstract retrieved.",
        "Similarity score above threshold — meaning relevant text was found.",
        "The language model explicitly judged the claim as not supported by the retrieved passage.",
        "Distinct from Insufficient Evidence: the source exists and was read, but the content does not back the claim.",
      ],
      note: null,
    },
    {
      color: "#6b21a8", bg: "#faf5ff", border: "#d8b4fe",
      label: "Hallucinated",
      anchor: "hallucinated",
      meaning: "The DOI in the citation is invalid, malformed, or does not resolve to any existing publication — the cited source may be entirely fabricated.",
      conditions: [
        "doi_status is INVALID or UNRESOLVABLE after attempting CrossRef → OpenAlex → Semantic Scholar → CORE resolution.",
        "This verdict is assigned by a deterministic safety rule, not by the language model.",
        "Note: a hallucinated verdict does not necessarily mean the claim itself is false, only that the cited source cannot be verified.",
      ],
      note: "This is the strongest signal of a fabricated citation.",
    },
    {
      color: "#6b7280", bg: "#f9fafb", border: "#d1d5db",
      label: "Insufficient Evidence",
      anchor: "insufficient-evidence",
      meaning: "The system could not retrieve enough text from the cited source to make a reliable determination — not because the claim is wrong, but because the evidence was unavailable or too thin.",
      conditions: [
        "Source unavailable: the DOI resolved but no full text or abstract could be retrieved (e.g. paywalled, not indexed by Unpaywall or CORE).",
        "Abstract only: only the abstract was retrieved; the claim could not be checked against the full paper body.",
        "Low similarity: the best retrieved chunk scored below the 0.50 threshold.",
        "LLM fallback: the language model returned a malformed or empty response and the pipeline fell back to this conservative verdict.",
      ],
      note: "If you have access to the source PDF, you can upload it manually on the results page to enable full re-verification.",
    },
  ]

  return (
    <div style={{
      display: "flex", justifyContent: "center",
      padding: "20px 24px 80px",
      marginTop: "-80px",
      paddingTop: "80px",
      position: "relative",
      backgroundImage: `url('/src/assets/background.png')`,
      backgroundSize: "60%",
      backgroundPosition: "center 350px",
      backgroundRepeat: "no-repeat",
      minHeight: "600px"
    }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(245,245,245,0.9)" }} />

      <div style={{ maxWidth: "900px", width: "100%", textAlign: "center", position: "relative", zIndex: 1 }}>

        <span style={{ background: "#dbeafe", color: "#1a3a6b", borderRadius: "20px", padding: "6px 16px", fontSize: "13px", fontWeight: "600" }}>
          AI - Powered Verification
        </span>

        <h1 style={{ fontWeight: "800", fontSize: "42px", color: "#111", margin: "24px 0 16px" }}>
          How verifAi works
        </h1>

        <p style={{ color: "#888", fontSize: "16px", marginBottom: "32px", lineHeight: "1.8" }}>
          verifAi uses a combination of document parsing, reference retrieval, and AI-powered reasoning to verify whether the claims in your paper are actually supported by their cited sources.
        </p>

        {/* 3 Tabs */}
        <div style={{ display: "inline-flex", border: "1px solid #1a3a6b", borderRadius: "8px", overflow: "hidden", marginBottom: "48px" }}>
          {[
            { key: 'general', label: 'General' },
            { key: 'technical', label: 'Technical' },
            { key: 'categories', label: 'Verdict Categories' },
          ].map((tab, i) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: "10px 24px", border: "none",
                borderLeft: i > 0 ? "1px solid #1a3a6b" : "none",
                cursor: "pointer", fontSize: "14px", fontWeight: "700",
                background: activeTab === tab.key ? "#1a3a6b" : "white",
                color: activeTab === tab.key ? "white" : "#1a3a6b",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* General Tab */}
        {activeTab === 'general' && (
          <div style={{ display: "flex", flexDirection: "column", gap: "24px", textAlign: "left" }}>
            {generalSteps.map((item) => (
              <div key={item.step} style={{ background: "white", borderRadius: "16px", padding: "32px", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", display: "flex", gap: "24px", alignItems: "flex-start" }}>
                <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: "#1a3a6b", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "700", fontSize: "20px", flexShrink: 0 }}>
                  {item.step}
                </div>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontWeight: "700", fontSize: "18px", color: "#111", margin: "0 0 10px" }}>{item.title}</h3>
                  <p style={{ color: "#444", fontSize: "15px", lineHeight: "1.7", marginBottom: "12px" }}>{item.description}</p>
                  <div style={{ background: "#f0f4ff", borderRadius: "8px", padding: "10px 14px" }}>
                    <p style={{ color: "#1a3a6b", fontSize: "13px", fontWeight: "600", margin: 0 }}>{item.detail}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Technical Tab */}
        {activeTab === 'technical' && (
          <div style={{ textAlign: "left" }}>
            <div style={{ textAlign: "center", marginBottom: "28px" }}>
              <p style={{ color: "#888", fontSize: "14px", lineHeight: "1.7", maxWidth: "640px", margin: "0 auto" }}>
                A closer look at the underlying methodology, intended for readers who want to assess the validity of the verification approach itself.
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
              {technicalSteps.map((item) => (
                <div key={item.step} style={{ background: "white", borderRadius: "16px", padding: "32px", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", display: "flex", gap: "24px", alignItems: "flex-start" }}>
                  <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: "#1a3a6b", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "700", fontSize: "20px", flexShrink: 0 }}>
                    {item.step}
                  </div>
                  <div style={{ flex: 1 }}>
                    <h3 style={{ fontWeight: "700", fontSize: "18px", color: "#111", margin: "0 0 12px" }}>{item.title}</h3>
                    <ul style={{ margin: 0, paddingLeft: "20px", display: "flex", flexDirection: "column", gap: "10px" }}>
                      {item.points.map((point, i) => (
                        <li key={i} style={{ fontSize: "14px", color: "#444", lineHeight: "1.7" }}>{point}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Categories Tab */}
        {activeTab === 'categories' && (
          <div style={{ textAlign: "left" }}>
            <div style={{ textAlign: "center", marginBottom: "28px" }}>
              <p style={{ color: "#888", fontSize: "14px", lineHeight: "1.7", maxWidth: "640px", margin: "0 auto" }}>
                Every claim is assigned one of five verdicts based on the evidence retrieved and the AI's analysis. Here's exactly what each one means and under which conditions it is assigned.
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {categories.map(cat => (
                <div key={cat.label} id={`category-${cat.anchor}`} style={{ background: "white", borderRadius: "16px", padding: "28px 32px", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", borderLeft: `4px solid ${cat.color}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "10px" }}>
                    <span style={{ fontSize: "13px", fontWeight: "700", color: cat.color, background: cat.bg, padding: "4px 14px", borderRadius: "99px", border: `1px solid ${cat.border}` }}>
                      {cat.label}
                    </span>
                  </div>
                  <p style={{ fontSize: "14px", color: "#333", lineHeight: "1.7", marginBottom: "14px" }}>{cat.meaning}</p>
                  <p style={{ fontSize: "12px", fontWeight: "700", color: "#888", letterSpacing: "1px", marginBottom: "8px" }}>CONDITIONS</p>
                  <ul style={{ margin: 0, paddingLeft: "20px", display: "flex", flexDirection: "column", gap: "6px", marginBottom: cat.note ? "12px" : 0 }}>
                    {cat.conditions.map((c, i) => (
                      <li key={i} style={{ fontSize: "13px", color: "#444", lineHeight: "1.6" }}>{c}</li>
                    ))}
                  </ul>
                  {cat.note && (
                    <div style={{ background: cat.bg, border: `1px solid ${cat.border}`, borderRadius: "8px", padding: "10px 14px", marginTop: "12px" }}>
                      <p style={{ fontSize: "13px", color: cat.color, margin: 0, fontWeight: "600" }}>i {cat.note}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* NOTE */}
        <div style={{ marginTop: "48px", background: "white", borderRadius: "16px", padding: "32px 40px", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", textAlign: "center" }}>
          <p style={{ fontSize: "13px", fontWeight: "600", color: "#1a3a6b", letterSpacing: "1px", marginBottom: "12px" }}>NOTE</p>
          <p style={{ color: "#666", fontSize: "15px", lineHeight: "1.7" }}>
            verifAi was developed as a student project at TUM Campus Heilbronn as part of the course "Foundations and Applications of Generative AI". The verification pipeline is continuously being improved. Some results may vary depending on the availability of cited sources and the complexity of the claims.
          </p>
        </div>

      </div>
    </div>
  )
}

export default HowItWorksPage