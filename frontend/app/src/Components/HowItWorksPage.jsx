function HowItWorksPage() {
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

        <p style={{ color: "#888", fontSize: "16px", marginBottom: "56px", lineHeight: "1.8" }}>
          verifAi uses a combination of document parsing, reference retrieval, and AI-powered reasoning to verify whether the claims in your paper are actually supported by their cited sources.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: "24px", textAlign: "left" }}>

          {[
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
          ].map((item) => (
            <div key={item.step} style={{ background: "white", borderRadius: "16px", padding: "32px", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", display: "flex", gap: "24px", alignItems: "flex-start" }}>
              <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: "#1a3a6b", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "700", fontSize: "20px", flexShrink: 0 }}>
                {item.step}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0px", marginBottom: "10px" }}>
                  <span style={{ fontSize: "22px" }}>{item.icon}</span>
                  <h3 style={{ fontWeight: "700", fontSize: "18px", color: "#111", margin: 0 }}>{item.title}</h3>
                </div>
                <p style={{ color: "#444", fontSize: "15px", lineHeight: "1.7", marginBottom: "12px" }}>{item.description}</p>
                <div style={{ background: "#f0f4ff", borderRadius: "8px", padding: "10px 14px" }}>
                  <p style={{ color: "#1a3a6b", fontSize: "13px", fontWeight: "600", margin: 0 }}>{item.detail}</p>
                </div>
              </div>
            </div>
          ))}

        </div>

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