import { useNavigate, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import CitationGraph from './CitationGraph'
import logo from '../assets/Logo_VerifAi.png'
import { generateVerificationPdf } from './pdfReport'
import { getVerificationResults } from '../api'
import Mascot from './Mascot.jsx'

// Maps backend support_status (+ doi_status) onto the UI's 4-category model.
// "hallucinated" has no direct backend equivalent yet - this treats an
// invalid/unresolvable DOI combined with NOT_SUPPORTED as hallucinated.
// Confirm this mapping with the backend team if it doesn't match their intent.
function mapToUiStatus(result) {
  const invalidDoi = result.doi_status && result.doi_status !== 'VALID'
  if (invalidDoi && result.support_status === 'NOT_SUPPORTED') return 'hallucinated'

  switch (result.support_status) {
    case 'SUPPORTED': return 'supported'
    case 'PARTIALLY_SUPPORTED': return 'partial'
    case 'NOT_SUPPORTED': return 'unsupported'
    case 'INSUFFICIENT_EVIDENCE': return 'insufficient'
    case 'NEEDS_HUMAN_REVIEW': return 'insufficient'
    default: return 'insufficient'
  }
}

function ResultsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const fileName = location.state?.fileName || "research_paper.pdf"
  const documentId = location.state?.documentId

  const [activeFilter, setActiveFilter] = useState('All')
  const [activeView, setActiveView] = useState('overview')
  const [citationFilter, setCitationFilter] = useState('all')

  const [claims, setClaims] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (!documentId) {
      navigate('/error')
      return
    }

    getVerificationResults(documentId)
      .then(data => {
        const mappedClaims = data.results.map((r, idx) => ({
          id: r.result_id || idx + 1,
          status: mapToUiStatus(r),
          text: `"${r.claim_text}" ${r.citation_text || ''}`.trim(),
          source: r.reference_title || r.citation_text || 'Unknown source',
          reasoning: r.explanation || 'No explanation available.',
          confidence: r.confidence ?? 0,
          warning: r.human_review_required
            ? 'Human review recommended - this result may need manual verification.'
            : undefined,
          doiResolved: r.doi_status === 'VALID',
        }))
        setClaims(mappedClaims)
      })
      .catch(err => navigate('/error'))
      .finally(() => setIsLoading(false))
  }, [documentId, navigate])

  const statusConfig = {
    supported: { label: "Supported", color: "#16a34a", bg: "#f0fdf4", border: "#86efac" },
    partial: { label: "Partially Supported", color: "#d97706", bg: "#fffbeb", border: "#fcd34d" },
    unsupported: { label: "Unsupported", color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
    hallucinated: { label: "Hallucinated", color: "#6b21a8", bg: "#faf5ff", border: "#d8b4fe" },
    insufficient: { label: "Insufficient Evidence", color: "#6b7280", bg: "#f3f4f6", border: "#d1d5db" },
  }

  const summaryItems = [
    { label: "Supported", count: claims.filter(c => c.status === 'supported').length, color: "#16a34a" },
    { label: "Partially supported", count: claims.filter(c => c.status === 'partial').length, color: "#d97706" },
    { label: "Unsupported", count: claims.filter(c => c.status === 'unsupported').length, color: "#dc2626" },
    { label: "Hallucinated", count: claims.filter(c => c.status === 'hallucinated').length, color: "#6b7280" },
  ]

  const totalClaims = claims.length
  const credibilityScore = totalClaims > 0
    ? Math.round(
        ((summaryItems[0].count + summaryItems[1].count * 0.5) / totalClaims) * 100
      )
    : 0

  const credibilityLabel = credibilityScore >= 80 ? "Reliable"
    : credibilityScore >= 50 ? "Partially Reliable"
    : "Low Reliability"

  const credibilityColor = credibilityScore >= 80 ? "#16a34a"
    : credibilityScore >= 50 ? "#d97706"
    : "#dc2626"

  const mascotMood = credibilityScore >= 80 ? "happy"
    : credibilityScore >= 50 ? "idle"
    : credibilityScore >= 25 ? "sad"
    : "shocked"

  const filters = [
    { label: "All", key: "all", color: "#1a3a6b", border: "#1a3a6b" },
    { label: "Supported", key: "supported", color: "#16a34a", border: "#86efac" },
    { label: "Partial", key: "partial", color: "#d97706", border: "#fcd34d" },
    { label: "Unsupported", key: "unsupported", color: "#dc2626", border: "#fca5a5" },
    { label: "Hallucinated", key: "hallucinated", color: "#6b21a8", border: "#d8b4fe" },
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

  const handleDownload = () => {
    generateVerificationPdf({ claims, statusConfig, summaryItems, fileName, logo })
  }

  if (isLoading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <p style={{ color: "#888", fontSize: "15px" }}>Loading verification results...</p>
      </div>
    )
  }

  return (
    <div style={{ background: "#f5f5f5", minHeight: "100vh", padding: "32px 40px" }}>

      <div style={{ display: "flex", gap: "24px", maxWidth: "1200px", margin: "0 auto" }}>

        <div style={{ width: "280px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "16px" }}>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0", textAlign: "center" }}>
            <p style={{ fontSize: "11px", fontWeight: "700", color: "#1a3a6b", letterSpacing: "1px", marginBottom: "16px" }}>CREDIBILITY SCORE</p>
            <div style={{ display: "flex", justifyContent: "center", marginBottom: "8px" }}>
              <Mascot mood={mascotMood} size={56} />
            </div>
            <div style={{ position: "relative", width: "120px", height: "120px", margin: "0 auto 12px" }}>
              <svg viewBox="0 0 120 120" width="120" height="120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#e0e0e0" strokeWidth="12"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke={credibilityColor} strokeWidth="12"
                  strokeDasharray={`${2 * Math.PI * 50 * (credibilityScore / 100)} ${2 * Math.PI * 50}`}
                  strokeDashoffset={2 * Math.PI * 50 * 0.25}
                  strokeLinecap="round" transform="rotate(-90 60 60)"/>
              </svg>
              <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", fontSize: "22px", fontWeight: "700", color: "#111" }}>{credibilityScore}%</div>
            </div>
            <p style={{ color: credibilityColor, fontWeight: "600", fontSize: "14px", marginBottom: "8px" }}>{credibilityLabel}</p>
            <p style={{ color: "#888", fontSize: "12px", lineHeight: "1.5" }}>Some claims are inaccurate or unsupported by their cited sources.</p>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "16px" }}>CLAIMS SUMMARY</p>
            {summaryItems.map(item => (
              <div key={item.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                <span style={{ fontSize: "13px", color: "#444", display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: item.color, display: "inline-block" }} />
                  {item.label}
                </span>
                <span style={{ fontSize: "13px", fontWeight: "600", color: "#111" }}>{item.count}</span>
              </div>
            ))}
            <div style={{ height: "8px", borderRadius: "99px", overflow: "hidden", marginTop: "12px", display: "flex" }}>
              {summaryItems.map(item => (
                <div
                  key={item.label}
                  style={{
                    width: totalClaims > 0 ? `${(item.count / totalClaims) * 100}%` : "0%",
                    background: item.color,
                  }}
                />
              ))}
            </div>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "16px 24px", border: "1px solid #e0e0e0", display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ background: "#eef2ff", borderRadius: "8px", padding: "10px", fontSize: "20px" }}>📄</div>
            <div>
              <p style={{ fontSize: "14px", fontWeight: "600", color: "#111" }}>{fileName}</p>
              <p style={{ fontSize: "12px", color: "#888" }}>{totalClaims} claims processed</p>
            </div>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "12px" }}>VIEW</p>
            <div style={{ display: "flex", border: "1px solid #1a3a6b", borderRadius: "8px", overflow: "hidden" }}>
              <button
                onClick={() => setActiveView('overview')}
                style={{
                  flex: 1, padding: "10px", border: "none", cursor: "pointer", fontSize: "14px", fontWeight: "700",
                  background: activeView === 'overview' ? "#1a3a6b" : "white",
                  color: activeView === 'overview' ? "white" : "#1a3a6b",
                }}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveView('citation')}
                style={{
                  flex: 1, padding: "10px", border: "none", borderLeft: "1px solid #1a3a6b", cursor: "pointer", fontSize: "14px", fontWeight: "700",
                  background: activeView === 'citation' ? "#1a3a6b" : "white",
                  color: activeView === 'citation' ? "white" : "#1a3a6b",
                }}
              >
                Network Graph
              </button>
            </div>
          </div>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "12px" }}>EXPORT</p>
            <button onClick={handleDownload} style={{ width: "100%", background: "#1a3a6b", color: "white", border: "none", borderRadius: "8px", padding: "12px", cursor: "pointer", fontSize: "14px", fontWeight: "600" }}>
              Download PDF report
            </button>
          </div>

        </div>

        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <h2 style={{ fontSize: "24px", fontWeight: "700", color: "#111", margin: 0 }}>Verification Results</h2>
            <button onClick={() => navigate('/')} style={{ border: "1px solid #ccc", background: "white", borderRadius: "8px", padding: "8px 20px", cursor: "pointer", fontSize: "14px", display: "flex", alignItems: "center", gap: "6px" }}>
              ← New document
            </button>
          </div>
          <p style={{ color: "#888", fontSize: "14px", marginBottom: "20px" }}>
            {totalClaims} claims checked · {claims.filter(c => c.doiResolved).length} DOIs resolved · {claims.filter(c => !c.doiResolved).length} unresolvable
          </p>

          {activeView === 'overview' && (
            <>
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

              {filteredClaims.length === 0 ? (
                <p style={{ color: "#888", fontSize: "14px", textAlign: "center", padding: "40px 0" }}>
                  No claims match this filter.
                </p>
              ) : (
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
                            {claim.doiResolved ? "DOI resolved" : "DOI unresolved"}
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
              )}
            </>
          )}

          {activeView === 'citation' && (
            <>
              <div style={{ display: "flex", gap: "8px", marginBottom: "24px", flexWrap: "wrap" }}>
                {filters.map((filter) => (
                  <button
                    key={filter.key}
                    onClick={() => setCitationFilter(filter.key)}
                    style={{
                      padding: "8px 16px", borderRadius: "99px", fontSize: "13px", fontWeight: "600", cursor: "pointer",
                      background: citationFilter === filter.key ? filter.color : "white",
                      color: citationFilter === filter.key ? "white" : filter.color,
                      border: `1px solid ${filter.border}`
                    }}>
                    {filter.label}
                  </button>
                ))}
              </div>

              <CitationGraph claims={claims} statusConfig={statusConfig} documentLabel={fileName} statusFilter={citationFilter} />
            </>
          )}

        </div>
      </div>
    </div>
  )
}

export default ResultsPage