import { useNavigate, useLocation } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import CitationGraph from './CitationGraph'
import logo from '../assets/Logo_VerifAi.png'
import { generateVerificationPdf } from './pdfReport'
import { getVerificationResults, uploadReferenceSourcePdf, prepareEvidence, startPipelineRun, getDocumentStatus, TERMINAL_SUCCESS_STATUSES, TERMINAL_FAILURE_STATUSES } from '../api'
function mapToUiStatus(result) {
  // An invalid/unresolvable DOI is the strongest signal of a fabricated
  // citation, regardless of which fallback status the backend assigned.
  if (result.doi_status === 'INVALID') return 'hallucinated'

  switch (result.support_status) {
    case 'SUPPORTED': return 'supported'
    case 'PARTIALLY_SUPPORTED': return 'partial'
    case 'NOT_SUPPORTED': return 'unsupported'
    case 'INSUFFICIENT_EVIDENCE': return 'insufficient'
    case 'NEEDS_HUMAN_REVIEW': return 'insufficient'
    default: return 'insufficient'
  }
}

// Heuristic hint for low-similarity "Insufficient Evidence" cases.
// This does NOT change the actual status - it's just an explanatory
// note for whoever is reviewing the results, since a low score could
// mean either "not covered in this source" or "retrieval missed the
// right passage due to wording differences" (the RAG vocabulary-gap
// issue noted by the backend team).
function getSimilarityHint(score) {
  if (score == null) return null
  if (score < 0.20) {
    return {
      label: `Low similarity score (${score.toFixed(2)})`,
      detail: "This may indicate the claim isn't covered in this source at all.",
    }
  }
  if (score < 0.50) {
    return {
      label: `Borderline similarity score (${score.toFixed(2)})`,
      detail: "This is close to the threshold - it may just mean the search didn't find the right passage due to differing wording, rather than the claim being unsupported.",
    }
  }
  return null
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

  const [refUploadStatus, setRefUploadStatus] = useState({})
  const [refUploadError, setRefUploadError] = useState({})
  const [flashUpload, setFlashUpload] = useState(false)
  const claimsListRef = useRef(null)

  const loadResults = () => {
    if (!documentId) {
      navigate('/error')
      return Promise.resolve()
    }
    return getVerificationResults(documentId)
      .then(data => {
        const mappedClaims = data.results.map((r, idx) => {
          const referenceId = r.reference_id ?? r.referenceId ?? r.ref_id ?? null
          if (!referenceId) {
            console.warn('No reference_id found on verification result:', r)
          }
          return {
            id: r.result_id || idx + 1,
            referenceId,
            status: mapToUiStatus(r),
            text: `"${r.claim_text}" ${r.citation_text || ''}`.trim(),
            source: r.reference_title || r.citation_text || 'Unknown source',
            reasoning: r.explanation || 'No explanation available.',
            confidence: r.confidence ?? 0,
            similarityScore: r.overall_similarity_score ?? null,
            warning: r.human_review_required
              ? 'Human review recommended - this result may need manual verification.'
              : undefined,
            doiResolved: r.doi_status === 'VALID',
          }
        })
        setClaims(mappedClaims)
      })
      .catch(err => navigate('/error'))
  }

  useEffect(() => {
    setIsLoading(true)
    loadResults().finally(() => setIsLoading(false))
  }, [documentId])

  const statusConfig = {
    supported: { label: "Supported", color: "#16a34a", bg: "#f0fdf4", border: "#86efac" },
    partial: { label: "Partially Supported", color: "#d97706", bg: "#fffbeb", border: "#fcd34d" },
    unsupported: { label: "Unsupported", color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
    hallucinated: { label: "Hallucinated", color: "#6b21a8", bg: "#faf5ff", border: "#d8b4fe" },
    insufficient: { label: "Insufficient Evidence", color: "#6b7280", bg: "#f9fafb", border: "#d1d5db" },
  }

  const summaryItems = [
    { label: "Supported", count: claims.filter(c => c.status === 'supported').length, color: "#16a34a" },
    { label: "Partially supported", count: claims.filter(c => c.status === 'partial').length, color: "#d97706" },
    { label: "Unsupported", count: claims.filter(c => c.status === 'unsupported').length, color: "#dc2626" },
    { label: "Hallucinated", count: claims.filter(c => c.status === 'hallucinated').length, color: "#6b21a8" },
    { label: "Insufficient evidence", count: claims.filter(c => c.status === 'insufficient').length, color: "#6b7280" },
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

  const filters = [
    { label: "All", key: "all", color: "#1a3a6b", border: "#1a3a6b" },
    { label: "Supported", key: "supported", color: "#16a34a", border: "#86efac" },
    { label: "Partial", key: "partial", color: "#d97706", border: "#fcd34d" },
    { label: "Unsupported", key: "unsupported", color: "#dc2626", border: "#fca5a5" },
    { label: "Hallucinated", key: "hallucinated", color: "#6b21a8", border: "#d8b4fe" },
    { label: "Insufficient Evidence", key: "insufficient", color: "#6b7280", border: "#d1d5db" },
  ]

  const filteredClaims = claims.filter(claim => {
    if (activeFilter === "All") return true
    if (activeFilter === "Supported") return claim.status === "supported"
    if (activeFilter === "Partial") return claim.status === "partial"
    if (activeFilter === "Unsupported") return claim.status === "unsupported"
    if (activeFilter === "Hallucinated") return claim.status === "hallucinated"
    if (activeFilter === "Insufficient Evidence") return claim.status === "insufficient"
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

  const jumpToUnresolvedSources = () => {
    setActiveView('overview')
    setActiveFilter('Insufficient Evidence')
    setTimeout(() => {
      claimsListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setFlashUpload(true)
      setTimeout(() => setFlashUpload(false), 1800)
    }, 80)
  }

  const handleManualReferenceUpload = async (claim, file) => {
  if (!file) return

  if (!claim.referenceId) {
    console.error('Cannot upload: claim has no referenceId.', claim)
    setRefUploadStatus(prev => ({ ...prev, [claim.id]: 'no-reference' }))
    return
  }

  setRefUploadStatus(prev => ({ ...prev, [claim.id]: 'uploading' }))
  setRefUploadError(prev => ({ ...prev, [claim.id]: null }))
  try {
    await uploadReferenceSourcePdf(claim.referenceId, file)
    await prepareEvidence(documentId)

    setRefUploadStatus(prev => ({ ...prev, [claim.id]: 'checking' }))

    // prepareEvidence only rebuilds evidence packages - it does NOT re-run
    // verification. Trigger a fresh pipeline run and poll until it's done,
    // then reload results so the new full text actually gets used.
    await startPipelineRun(documentId)

    await new Promise((resolve, reject) => {
      const poll = setInterval(async () => {
        try {
          const status = await getDocumentStatus(documentId)
          const pct = status.progress_percentage ?? 0
          if (TERMINAL_SUCCESS_STATUSES.includes(status.status) || pct >= 100) {
            clearInterval(poll)
            resolve()
          } else if (TERMINAL_FAILURE_STATUSES.includes(status.status)) {
            clearInterval(poll)
            reject(new Error('Re-verification failed.'))
          }
        } catch (err) {
          clearInterval(poll)
          reject(err)
        }
      }, 2000)
    })

    await loadResults()
    setRefUploadStatus(prev => {
      const next = { ...prev }
      delete next[claim.id]
      return next
    })
  } catch (err) {
    console.error('Reference upload failed:', err)
    setRefUploadStatus(prev => ({ ...prev, [claim.id]: 'error' }))
    setRefUploadError(prev => ({ ...prev, [claim.id]: err.message }))
  }
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

      <style>{`
        @keyframes verifai-dot-pulse {
          0%, 80%, 100% { opacity: 0.2; }
          40% { opacity: 1; }
        }
        @keyframes verifai-step-spin {
          to { transform: rotate(360deg); }
        }
        @keyframes verifai-flash-highlight {
          0%, 100% { background: #f9fafb; border-color: #d1d5db; box-shadow: none; }
          25%, 75% { background: #eef2ff; border-color: #1a3a6b; box-shadow: 0 0 0 3px rgba(26,58,107,0.15); }
        }
      `}</style>

      <div style={{ display: "flex", gap: "24px", maxWidth: "1200px", margin: "0 auto" }}>

        <div style={{ width: "280px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "16px" }}>

          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0", textAlign: "center" }}>
            <p style={{ fontSize: "11px", fontWeight: "700", color: "#1a3a6b", letterSpacing: "1px", marginBottom: "16px" }}>CREDIBILITY SCORE</p>
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
            <div style={{ background: "#eef2ff", borderRadius: "8px", padding: "10px", fontSize: "20px", flexShrink: 0 }}>📄</div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <p
                title={fileName}
                style={{
                  fontSize: "14px", fontWeight: "600", color: "#111",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"
                }}
              >
                {fileName}
              </p>
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

          {summaryItems[4].count > 0 && (
            <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
              <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "8px" }}>UNRESOLVED SOURCES</p>
              <p style={{ fontSize: "12px", color: "#888", marginBottom: "14px", lineHeight: "1.5" }}>
                {summaryItems[4].count} claim(s) couldn't be checked automatically.
              </p>
              <button
                onClick={jumpToUnresolvedSources}
                style={{
                  width: "100%", background: "white", color: "#1a3a6b",
                  border: "1px solid #1a3a6b",
                  borderRadius: "8px", padding: "12px", cursor: "pointer",
                  fontSize: "13px", fontWeight: "600"
                }}>
                Add reference documents to check claims
              </button>
            </div>
          )}

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
              <div ref={claimsListRef} style={{ display: "flex", gap: "8px", marginBottom: "24px", flexWrap: "wrap" }}>
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
                    const showManualUpload = !claim.doiResolved || claim.status === 'insufficient'
                    const uploadState = refUploadStatus[claim.id]
                    const similarityHint = claim.status === 'insufficient'
                      ? getSimilarityHint(claim.similarityScore)
                      : null
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

                        <div style={{ background: "#f8f8f8", borderRadius: "8px", padding: "16px", marginBottom: claim.warning || similarityHint ? "12px" : "16px" }}>
                          <p style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "1px", marginBottom: "8px" }}>AI REASONING</p>
                          <p style={{ fontSize: "13px", color: "#444", lineHeight: "1.6" }}>{claim.reasoning}</p>
                        </div>

                        {similarityHint && (
                          <div style={{ background: "#f3f4f6", border: "1px solid #d1d5db", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                            <p style={{ fontSize: "13px", fontWeight: "600", color: "#4b5563", marginBottom: "4px" }}>
                              ⚠ {similarityHint.label}
                            </p>
                            <p style={{ fontSize: "12px", color: "#6b7280", lineHeight: "1.5" }}>
                              {similarityHint.detail}
                            </p>
                          </div>
                        )}

                        {claim.warning && (
                          <div style={{ background: "#fffbeb", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                            <p style={{ fontSize: "13px", color: "#d97706", lineHeight: "1.5" }}>{claim.warning}</p>
                          </div>
                        )}

                        {showManualUpload && (
                          <div style={{
                            background: "#f9fafb", border: "1px dashed #d1d5db", borderRadius: "8px",
                            padding: "12px 16px", marginBottom: "16px",
                            animation: flashUpload ? "verifai-flash-highlight 0.6s ease-in-out 2" : "none",
                          }}>
                            {uploadState === 'checking' ? (
                              <p style={{ fontSize: "13px", color: "#1a3a6b", display: "flex", alignItems: "center", gap: "2px" }}>
                                Re-checking this claim automatically
                                <span style={{ display: "inline-flex", gap: "2px", marginLeft: "4px" }}>
                                  <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: "#1a3a6b", animation: "verifai-dot-pulse 1.2s infinite", animationDelay: "0s" }} />
                                  <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: "#1a3a6b", animation: "verifai-dot-pulse 1.2s infinite", animationDelay: "0.2s" }} />
                                  <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: "#1a3a6b", animation: "verifai-dot-pulse 1.2s infinite", animationDelay: "0.4s" }} />
                                </span>
                              </p>
                            ) : (
                              <>
                                <input
                                  type="file"
                                  accept=".pdf"
                                  id={`ref-upload-${claim.id}`}
                                  style={{ display: "none" }}
                                  onChange={(e) => {
                                    const file = e.target.files[0]
                                    if (file) handleManualReferenceUpload(claim, file)
                                  }}
                                />
                                <button
                                  type="button"
                                  onClick={() => document.getElementById(`ref-upload-${claim.id}`).click()}
                                  disabled={uploadState === 'uploading'}
                                  style={{
                                    fontSize: "13px", color: "#1a3a6b", background: "none",
                                    border: "none", cursor: "pointer",
                                    fontWeight: "600", padding: 0, display: "flex", alignItems: "center", gap: "6px"
                                  }}>
                                  {uploadState === 'uploading' ? (
                                    <>
                                      <span style={{
                                        width: "12px", height: "12px", borderRadius: "50%",
                                        border: "2px solid #c5cfe0", borderTopColor: "#1a3a6b",
                                        animation: "verifai-step-spin 0.8s linear infinite", display: "inline-block"
                                      }} />
                                      Uploading...
                                    </>
                                  ) : (
                                    "📎 Add the reference manually"
                                  )}
                                </button>
                                <p style={{ fontSize: "11px", color: "#aaa", marginTop: "6px" }}>
                                  PDF only, max. 15 MB
                                </p>
                                {uploadState === 'error' && (
                                  <p style={{ fontSize: "12px", color: "#dc2626", marginTop: "6px" }}>
                                    {refUploadError[claim.id] || "Upload failed, please try again."}
                                  </p>
                                )}
                                {uploadState === 'no-reference' && (
                                  <p style={{ fontSize: "12px", color: "#dc2626", marginTop: "6px" }}>
                                    This claim has no linked reference ID - manual upload isn't possible here.
                                  </p>
                                )}
                              </>
                            )}
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

          <div style={{ marginTop: "40px", paddingTop: "24px", borderTop: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#888", letterSpacing: "1px", marginBottom: "16px" }}>
              UNDERSTANDING THESE RESULTS
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "16px" }}>
              {Object.values(statusConfig).map(item => (
                <div key={item.label} style={{
                  display: "flex", alignItems: "center", gap: "8px",
                  background: item.bg, border: `1px solid ${item.border}`,
                  borderRadius: "8px", padding: "8px 14px"
                }}>
                  <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: item.color, flexShrink: 0 }} />
                  <span style={{ fontSize: "13px", color: "#333" }}>{item.label}</span>
                </div>
              ))}
            </div>
            <p style={{ fontSize: "13px", color: "#888", lineHeight: "1.6" }}>
              Not sure how a verdict is determined, or why some sources can't be checked automatically?{' '}
              <a href="/how-it-works" style={{ color: "#1a3a6b", fontWeight: "600", textDecoration: "underline" }}>
                See how VerifAi works →
              </a>
            </p>
          </div>

        </div>
      </div>
    </div>
  )
}

export default ResultsPage