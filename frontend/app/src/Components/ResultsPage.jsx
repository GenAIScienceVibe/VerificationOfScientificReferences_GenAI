import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

function ResultsPage() {
  const navigate = useNavigate()
  const [activeFilter, setActiveFilter] = useState('All')

  const claims = [
    {
      id: 1,
      status: "supported",
      text: '"Regular exercise reduces the risk of heart disease by 35% [Johnson et al., 2019]"',
      source: "Johnson et al., 2019",
      reasoning: "The cited source explicitly reports a 35% reduction in cardiovascular events among participants in the exercise intervention arm, directly supporting the claim as stated.",
      confidence: 0.91,
    },
    {
      id: 2,
      status: "partial",
      text: '"Drug X reduces fever in 80% of cases within 2 hours of administration [Smith et al., 2021]"',
      source: "Smith et al., 2021",
      reasoning: "The referenced paper reports a 28% reduction, not 80% as claimed. The timeframe of 2 hours is consistent with the source, but the efficacy figure is significantly overstated.",
      confidence: 0.62,
      warning: "Human review recommended - the discrepancy in figures may indicate a data entry error or intentional misrepresentation.",
    },
    {
      id: 3,
      status: "unsupported",
      text: '"Study shows X causes Y in 100% of cases [Brown et al., 2020]"',
      source: "Brown et al., 2020",
      reasoning: "The cited source does not support this claim. No such statistic was found in the referenced paper.",
      confidence: 0.21,
    },
    {
      id: 4,
      status: "hallucinated",
      text: '"Research proves Z is always true [White et al., 2022]"',
      source: "White et al., 2022",
      reasoning: "No such paper exists. The citation appears to be fabricated.",
      confidence: 0.05,
    },
  ]

  const statusConfig = {
    supported: { label: "Supported", color: "#16a34a", bg: "#f0fdf4", border: "#86efac" },
    partial: { label: "Partially Supported", color: "#d97706", bg: "#fffbeb", border: "#fcd34d" },
    unsupported: { label: "Unsupported", color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
    hallucinated: { label: "Hallucinated", color: "#6b21a8", bg: "#faf5ff", border: "#d8b4fe" },
  }

  const filters = [
    { label: "All", color: "#1a3a6b", border: "#1a3a6b" },
    { label: "Supported", color: "#16a34a", border: "#86efac" },
    { label: "Partial", color: "#d97706", border: "#fcd34d" },
    { label: "Unsupported", color: "#dc2626", border: "#fca5a5" },
    { label: "Hallucinated", color: "#6b21a8", border: "#d8b4fe" },
  ]

  const filteredClaims = claims.filter(claim => {
    if (activeFilter === "All") return true
    if (activeFilter === "Supported") return claim.status === "supported"
    if (activeFilter === "Partial") return claim.status === "partial"
    if (activeFilter === "Unsupported") return claim.status === "unsupported"
    if (activeFilter === "Hallucinated") return claim.status === "hallucinated"
    return true
  })

  const getConfidenceColor = (c) => {
    if (c > 0.7) return "#16a34a"
    if (c > 0.4) return "#d97706"
    return "#dc2626"
  }

  return (
    <div style={{ background: "#f5f5f5", minHeight: "100vh" }}>

      <div style={{ background: "white", borderBottom: "1px solid #eee", padding: "12px 40px", display: "flex", justifyContent: "flex-end", gap: "12px" }}>
        <button onClick={() => navigate('/')} style={{ border: "1px solid #ccc", background: "white", borderRadius: "8px", padding: "8px 20px", cursor: "pointer", fontSize: "14px" }}>
          New document
        </button>
        <a href="#" download style={{ border: "1px solid #ccc", background: "white", borderRadius: "8px", padding: "8px 20px", cursor: "pointer", fontSize: "14px", textDecoration: "none", color: "#444" }}>
          Download PDF
        </a>
      </div>

      <div style={{ display: "flex", gap: "24px", padding: "32px 40px", maxWidth: "1200px", margin: "0 auto" }}>

        <div style={{ width: "280px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "16px" }}>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0", textAlign: "center" }}>
            <p style={{ fontSize: "11px", fontWeight: "700", color: "#1a3a6b", letterSpacing: "1px", marginBottom: "16px" }}>CREDIBILITY SCORE</p>
            <div style={{ position: "relative", width: "120px", height: "120px", margin: "0 auto 12px" }}>
              <svg viewBox="0 0 120 120" width="120" height="120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#e0e0e0" strokeWidth="12"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke="#1a3a6b" strokeWidth="12"
                  strokeDasharray={`${2 * Math.PI * 50 * 0.72} ${2 * Math.PI * 50}`}
                  strokeDashoffset={2 * Math.PI * 50 * 0.25}
                  strokeLinecap="round" transform="rotate(-90 60 60)"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke="#d97706" strokeWidth="12"
                  strokeDasharray={`${2 * Math.PI * 50 * 0.28} ${2 * Math.PI * 50}`}
                  strokeDashoffset={-2 * Math.PI * 50 * 0.47}
                  strokeLinecap="round" transform="rotate(-90 60 60)"/>
              </svg>
              <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", fontSize: "22px", fontWeight: "700", color: "#111" }}>72%</div>
            </div>
            <p style={{ color: "#d97706", fontWeight: "600", fontSize: "14px", marginBottom: "8px" }}>Partially Reliable</p>
            <p style={{ color: "#888", fontSize: "12px", lineHeight: "1.5" }}>Some claims are inaccurate or unsupported by their cited sources.</p>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "16px" }}>CLAIMS SUMMARY</p>
            {[
              { label: "Supported", count: 8, color: "#16a34a" },
              { label: "Partially supported", count: 3, color: "#d97706" },
              { label: "Unsupported", count: 2, color: "#dc2626" },
              { label: "Hallucinated", count: 4, color: "#6b7280" },
            ].map(item => (
              <div key={item.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                <span style={{ fontSize: "13px", color: "#444", display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: item.color, display: "inline-block" }} />
                  {item.label}
                </span>
                <span style={{ fontSize: "13px", fontWeight: "600", color: "#111" }}>{item.count}</span>
              </div>
            ))}
            <div style={{ height: "8px", borderRadius: "99px", overflow: "hidden", marginTop: "12px", display: "flex" }}>
              <div style={{ width: "47%", background: "#16a34a" }} />
              <div style={{ width: "18%", background: "#d97706" }} />
              <div style={{ width: "12%", background: "#dc2626" }} />
              <div style={{ width: "23%", background: "#6b7280" }} />
            </div>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "16px 24px", border: "1px solid #e0e0e0", display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ background: "#eef2ff", borderRadius: "8px", padding: "10px", fontSize: "20px" }}>📄</div>
            <div>
              <p style={{ fontSize: "14px", fontWeight: "600", color: "#111" }}>research_paper.pdf</p>
              <p style={{ fontSize: "12px", color: "#888" }}>17 claims processed just now</p>
            </div>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "12px" }}>EXPORT</p>
            <a href="#" download style={{ width: "100%", background: "#1a3a6b", color: "white", border: "none", borderRadius: "8px", padding: "12px", cursor: "pointer", fontSize: "14px", fontWeight: "600", display: "block", textAlign: "center", textDecoration: "none" }}>
              Download PDF report
            </a>
          </div>

        </div>

        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: "24px", fontWeight: "700", color: "#111", marginBottom: "8px" }}>Verification Results</h2>
          <p style={{ color: "#888", fontSize: "14px", marginBottom: "20px" }}>17 claims checked · 10 DOIs resolved · 2 unresolvable</p>

          <div style={{ display: "flex", gap: "8px", marginBottom: "24px", flexWrap: "wrap" }}>
            {filters.map((filter) => (
              <button
                key={filter.label}
                onClick={() => setActiveFilter(filter.label)}
                style={{
                  padding: "8px 16px", borderRadius: "99px", fontSize: "13px", fontWeight: "600", cursor: "pointer",
                  background: activeFilter === filter.label ? filter.color : "white",
                  color: activeFilter === filter.label ? "white" : filter.color,
                  border: `1px solid ${filter.border}`
                }}>
                {filter.label}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {filteredClaims.map(claim => {
              const config = statusConfig[claim.status]
              return (
                <div key={claim.id} style={{ background: "white", borderRadius: "12px", padding: "24px", border: `1px solid ${config.border}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                    <span style={{ fontSize: "12px", fontWeight: "700", color: "#888", letterSpacing: "1px" }}>CLAIM {claim.id}</span>
                    <span style={{ fontSize: "12px", fontWeight: "700", color: config.color, background: config.bg, padding: "4px 12px", borderRadius: "99px", border: `1px solid ${config.border}` }}>
                      {config.label}
                    </span>
                  </div>

                  <p style={{ fontSize: "14px", color: "#333", marginBottom: "16px", lineHeight: "1.6" }}>{claim.text}</p>

                  <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
                    <span style={{ fontSize: "12px", color: "#555", background: "#f5f5f5", padding: "4px 12px", borderRadius: "99px", border: "1px solid #e0e0e0" }}>
                      {claim.source}
                    </span>
                    <span style={{ fontSize: "12px", color: "#555", background: "#f5f5f5", padding: "4px 12px", borderRadius: "99px", border: "1px solid #e0e0e0" }}>
                      DOI resolved
                    </span>
                  </div>

                  <div style={{ background: "#f8f8f8", borderRadius: "8px", padding: "16px", marginBottom: claim.warning ? "12px" : "16px" }}>
                    <p style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "1px", marginBottom: "8px" }}>AI REASONING</p>
                    <p style={{ fontSize: "13px", color: "#444", lineHeight: "1.6" }}>{claim.reasoning}</p>
                  </div>

                  {claim.warning && (
                    <div style={{ background: "#fffbeb", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                      <p style={{ fontSize: "13px", color: "#d97706", lineHeight: "1.5" }}>{claim.warning}</p>
                    </div>
                  )}

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "12px", color: "#888" }}>Confidence</span>
                      <div style={{ width: "80px", height: "6px", background: "#e0e0e0", borderRadius: "99px", overflow: "hidden" }}>
                        <div style={{ width: `${claim.confidence * 100}%`, height: "6px", background: getConfidenceColor(claim.confidence), borderRadius: "99px" }} />
                      </div>
                      <span style={{ fontSize: "12px", color: "#888" }}>{claim.confidence}</span>
                    </div>
                    <button style={{ fontSize: "12px", color: "#888", background: "none", border: "none", cursor: "pointer" }}>
                      Show source passage
                    </button>
                  </div>

                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default ResultsPage