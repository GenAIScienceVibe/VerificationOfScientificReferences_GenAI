import { useState } from 'react'

function HowItWorksPage() {
  const [activeTab, setActiveTab] = useState('general')

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
        "Once a source is resolved, verifAi attempts full-text retrieval via Unpaywall (legal open-access PDF discovery) and CORE (full-text API fallback) before falling back to abstract-only evidence. Some publishers report open-access status without exposing a programmatically retrievable PDF (requiring a separate licensed text-mining API we do not hold); in these cases users can upload the source PDF manually to enable full re-verification.",
      ],
    },
    {
      step: 3,
      title: "Evidence Retrieval & Verification (RAG + LLM)",
      points: [
        "Retrieved text is chunked and embedded (OpenAI-compatible embedding model, accessed via OpenRouter), and the resulting vectors are indexed for similarity search against the claim text using cosine similarity.",
        "A configurable similarity threshold (currently 0.50) determines whether retrieved evidence is considered strong enough to support a verdict; scores below this threshold are flagged as insufficient evidence rather than treated as a negative result. Short, informally-phrased claims and dense academic source text can sit in different regions of embedding space (a 'vocabulary gap'), which can suppress similarity scores even when the underlying content is relevant - Hypothetical Document Embeddings (HyDE) is a documented future mitigation, not yet enabled.",
        "A language model receives the claim and its retrieved evidence and produces a structured verdict (Supported / Partially Supported / Not Supported) with a written justification, rather than a single opaque confidence number.",
      ],
    },
    {
      step: 4,
      title: "Safety Policy & Reporting",
      points: [
        "A deterministic safety policy layer sits on top of the LLM output and can override or cap its verdict based on independently-checked conditions: DOI validity, evidence availability tier (full text vs. abstract-only vs. unavailable), and similarity score - preventing the system from expressing high confidence when the underlying evidence is weak, regardless of what the LLM itself reports.",
        "Claims with an invalid or unresolvable DOI are treated as a strong fabrication signal. Claims where evidence could be retrieved but a malformed model response is encountered (an occasional LLM reliability issue, under active investigation) are routed to a conservative human-review state rather than silently defaulting to a verdict.",
        "An exact-match verification cache avoids redundant re-verification when multiple claims cite the same source. The final credibility score and PDF report are generated client-side via jsPDF.",
      ],
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
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        background: "rgba(245,245,245,0.9)"
      }} />

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

        <div style={{ display: "inline-flex", border: "1px solid #1a3a6b", borderRadius: "8px", overflow: "hidden", marginBottom: "48px" }}>
          <button
            onClick={() => setActiveTab('general')}
            style={{
              padding: "10px 28px", border: "none", cursor: "pointer", fontSize: "14px", fontWeight: "700",
              background: activeTab === 'general' ? "#1a3a6b" : "white",
              color: activeTab === 'general' ? "white" : "#1a3a6b",
            }}
          >
            General
          </button>
          <button
            onClick={() => setActiveTab('technical')}
            style={{
              padding: "10px 28px", border: "none", borderLeft: "1px solid #1a3a6b", cursor: "pointer", fontSize: "14px", fontWeight: "700",
              background: activeTab === 'technical' ? "#1a3a6b" : "white",
              color: activeTab === 'technical' ? "white" : "#1a3a6b",
            }}
          >
            Technical
          </button>
        </div>

        {activeTab === 'general' ? (
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
        ) : (
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
                        <li key={i} style={{ color: "#444", fontSize: "14px", lineHeight: "1.7" }}>{point}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

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