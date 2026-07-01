import { useNavigate, useLocation } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import CitationGraph from './CitationGraph'
import logo from '../assets/Logo_VerifAi.png'
import { generateVerificationPdf } from './pdfReport'
import { getVerificationResults, getVerificationResult, getDocumentReferences, uploadReferenceSourcePdf, prepareEvidence, startPipelineRun, getDocumentStatus, TERMINAL_SUCCESS_STATUSES, TERMINAL_FAILURE_STATUSES } from '../api'

const STATUS_TOOLTIPS = {
  supported: "The claim is directly backed by the cited source — the AI found matching evidence and the source confirms the statement.",
  partial: "The cited source partially supports the claim — some aspects match, but not all details are confirmed.",
  unsupported: "The cited source does not support this claim — the AI found the source but the content contradicts or omits the claim.",
  hallucinated: "The cited source could not be verified — the DOI is invalid or the reference does not appear to exist.",
  insufficient: "There wasn't enough accessible text from the source to make a reliable determination. This may be due to a paywall or limited open-access availability.",
}

const STATUS_ANCHOR = {
  supported: "supported",
  partial: "partially-supported",
  unsupported: "unsupported",
  hallucinated: "hallucinated",
  insufficient: "insufficient-evidence",
}

const CONFIDENCE_TOOLTIP = "Confidence reflects how certain the AI is about its verdict, based on how closely the retrieved source text matched the claim (similarity score) and how clearly the LLM could determine a verdict. A high score means the evidence was clear and unambiguous."

const CREDIBILITY_TOOLTIP = "The credibility score summarises how well-supported the claims in this document are overall. It is calculated as: (Supported x 1.0 + Partially Supported x 0.5) / Total Claims x 100. A score above 80% is considered Reliable, 50-80% Partially Reliable, and below 50% Low Reliability."

function mapToUiStatus(result) {
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

function getEvidenceAvailabilityHint(evidenceAvailability, status) {
  if (status !== 'insufficient') return null
  if (evidenceAvailability === 'ABSTRACT_AVAILABLE') {
    return {
      label: 'Abstract only',
      detail: 'Only the abstract was retrieved for this source — full-text verification was not possible. Upload the full paper PDF below to re-check this claim.',
    }
  }
  if (evidenceAvailability === 'SOURCE_UNAVAILABLE') {
    return {
      label: 'Source unavailable',
      detail: 'The full text of this source could not be retrieved (e.g. paywalled or not indexed). Upload the PDF below to enable verification.',
    }
  }
  return null
}

function getDoiStatusExplanation(doiStatus, evidenceAvailability) {
  switch (doiStatus) {
    case 'VALID':
      if (evidenceAvailability === 'SOURCE_UNAVAILABLE')
        return { text: 'DOI resolved, but full text is not publicly accessible (paywalled or not indexed).', color: '#d97706' }
      if (evidenceAvailability === 'ABSTRACT_AVAILABLE')
        return { text: 'DOI resolved, but only the abstract could be retrieved — full-text verification was not possible.', color: '#d97706' }
      if (evidenceAvailability === 'PREPRINT_AVAILABLE')
        return { text: 'DOI resolved to a preprint — contents may differ from the final published version.', color: '#d97706' }
      return null
    case 'INVALID':
      return null
    case 'UNRESOLVABLE':
      return { text: 'The DOI was found but could not be resolved — the source may be unavailable, retracted, or incorrectly cited.', color: '#dc2626' }
    case 'MISSING':
      return { text: 'No DOI found in the reference — lookup relied on title and author metadata only, which is less reliable.', color: '#d97706' }
    default:
      return null
  }
}

function getSimilarityHint(score) {
  if (score == null) return null
  if (score < 0.20) return {
    label: `Low similarity score (${score.toFixed(2)})`,
    detail: "This may indicate the claim isn't covered in this source at all.",
  }
  if (score < 0.50) return {
    label: `Borderline similarity score (${score.toFixed(2)})`,
    detail: "This is close to the threshold - it may just mean the search didn't find the right passage due to differing wording, rather than the claim being unsupported.",
  }
  return null
}

function ResultsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const fileName = location.state?.fileName || "research_paper.pdf"
  const documentId = location.state?.documentId

  const [activeFilter, setActiveFilter] = useState('All')
  const [sortBy, setSortBy] = useState('default')
  const [activeView, setActiveView] = useState('overview')
  const [citationFilter, setCitationFilter] = useState('all')
  const [claims, setClaims] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [refUploadStatus, setRefUploadStatus] = useState({})
  const [refUploadError, setRefUploadError] = useState({})
  const [expandedPassages, setExpandedPassages] = useState({})
  const [expandedReasoning, setExpandedReasoning] = useState({})
  const [passageData, setPassageData] = useState({})
  const [flashUpload, setFlashUpload] = useState(false)
  const claimsListRef = useRef(null)

  const loadResults = () => {
    if (!documentId) {
      navigate('/error')
      return Promise.resolve()
    }
    return Promise.all([
      getVerificationResults(documentId),
      getDocumentReferences(documentId).catch(() => ({ references: [] })),
    ])
      .then(([data, refData]) => {
        const refMap = {}
        for (const ref of (refData?.references ?? [])) {
          if (ref.reference_id) {
            refMap[ref.reference_id] = {
              authors: ref.extracted_authors ?? null,
              year: ref.extracted_year ?? null,
            }
          }
        }
        const mappedClaims = data.results.map((r, idx) => {
          const referenceId = r.reference_id ?? r.referenceId ?? r.ref_id ?? null
          if (!referenceId) console.warn('No reference_id found on verification result:', r)
          const refInfo = referenceId ? (refMap[referenceId] ?? null) : null
          const hasAuthors = !!refInfo?.authors
          const authorLine = hasAuthors
            ? `${refInfo.authors}${refInfo.year ? ` (${refInfo.year})` : ''}`
            : null
          return {
            id: r.result_id,
            displayId: idx + 1,
            referenceId,
            status: mapToUiStatus(r),
            text: `"${r.claim_text}" ${r.citation_text || ''}`.trim(),
            source: r.reference_title
              ? hasAuthors ? r.reference_title : `${r.reference_title}${r.citation_text ? `  ·  ${r.citation_text}` : ''}`
              : r.citation_text || 'Unknown source',
            authorLine,
            reasoning: (r.explanation || 'No explanation available.')
              .replace(/Reused cached verification result result_[a-z0-9]+\.\s*/gi, '')
              .trim() || 'No explanation available.',
            confidence: r.confidence ?? 0,
            similarityScore: r.overall_similarity_score ?? null,
            evidenceAvailability: r.evidence_availability ?? null,
            safetyRules: r.safety_rules_triggered ?? [],
            warning: r.human_review_required
              ? 'Human review recommended - this result may need manual verification.'
              : undefined,
            doiResolved: r.doi_status === 'VALID',
            doiStatus: r.doi_status ?? null,
doiUrl: r.doi ? `https://doi.org/${r.doi}` : null,
          }
        })
        setClaims(mappedClaims)
      })
      .catch(() => navigate('/error'))
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
    ? Math.round(((summaryItems[0].count + summaryItems[1].count * 0.5) / totalClaims) * 1000) / 10
    : 0

  const credibilityLabel = credibilityScore >= 80 ? "Reliable"
    : credibilityScore >= 50 ? "Partially Reliable" : "Low Reliability"
  const credibilityColor = credibilityScore >= 80 ? "#16a34a"
    : credibilityScore >= 50 ? "#d97706" : "#dc2626"

  const filters = [
    { label: "All", key: "all", color: "#1a3a6b", border: "#1a3a6b" },
    { label: "Supported", key: "supported", color: "#16a34a", border: "#86efac" },
    { label: "Partial", key: "partial", color: "#d97706", border: "#fcd34d" },
    { label: "Unsupported", key: "unsupported", color: "#dc2626", border: "#fca5a5" },
    { label: "Hallucinated", key: "hallucinated", color: "#6b21a8", border: "#d8b4fe" },
    { label: "Insufficient Evidence", key: "insufficient", color: "#6b7280", border: "#d1d5db" },
  ]

  const sortOrder = { supported: 0, partial: 1, unsupported: 2, hallucinated: 3, insufficient: 4 }
  const sortedClaims = [...claims].sort((a, b) => {
    if (sortBy === 'confidence') return b.confidence - a.confidence
    if (sortBy === 'status') return (sortOrder[a.status] ?? 5) - (sortOrder[b.status] ?? 5)
    if (sortBy === 'source') return (a.source || '').localeCompare(b.source || '')
    if (sortBy === 'author') return (a.authorLine || '').localeCompare(b.authorLine || '')
    return (a.displayId ?? 0) - (b.displayId ?? 0)
  })

  const filteredClaims = sortedClaims.filter(claim => {
    if (activeFilter === "All") return true
    if (activeFilter === "Supported") return claim.status === "supported"
    if (activeFilter === "Partial") return claim.status === "partial"
    if (activeFilter === "Unsupported") return claim.status === "unsupported"
    if (activeFilter === "Hallucinated") return claim.status === "hallucinated"
    if (activeFilter === "Insufficient Evidence") return claim.status === "insufficient"
    return true
  })

  const getHumanReviewReason = (doiStatus, evidenceAvailability) => {
    if (doiStatus === 'INVALID' || doiStatus === 'UNRESOLVABLE')
      return 'The DOI does not resolve to an existing publication — this citation may not exist or could be fabricated.'
    if (doiStatus === 'MISSING')
      return 'No DOI was found for this reference, so the source could not be automatically located.'
    if (doiStatus === 'MALFORMED')
      return 'The DOI in this reference is malformed and could not be looked up.'
    if (evidenceAvailability === 'METADATA_ONLY')
      return 'The source was found but only metadata is available — the full text could not be accessed to check the claim.'
    return 'The source was found but there was not enough evidence to confidently verify this claim automatically.'
  }

  const getConfidenceColor = (c) => c > 0.7 ? "#16a34a" : c > 0.4 ? "#d97706" : "#dc2626"
  const handleDownload = async () => {
    try {
      await generateVerificationPdf({ claims, statusConfig, summaryItems, fileName, logo, credibilityScore, credibilityLabel, credibilityColor })
    } catch (err) {
      console.error('PDF generation failed:', err)
      alert('PDF generation failed: ' + err.message)
    }
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
      await startPipelineRun(documentId)
      await new Promise((resolve, reject) => {
        const poll = setInterval(async () => {
          try {
            const status = await getDocumentStatus(documentId)
            const pct = status.progress_percentage ?? 0
            if (TERMINAL_SUCCESS_STATUSES.includes(status.status) || pct >= 100) { clearInterval(poll); resolve() }
            else if (TERMINAL_FAILURE_STATUSES.includes(status.status)) { clearInterval(poll); reject(new Error('Re-verification failed.')) }
          } catch (err) { clearInterval(poll); reject(err) }
        }, 2000)
      })
      await loadResults()
      setRefUploadStatus(prev => { const next = { ...prev }; delete next[claim.id]; return next })
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
        @keyframes verifai-dot-pulse { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }
        @keyframes verifai-step-spin { to { transform: rotate(360deg); } }
        @keyframes verifai-flash-highlight {
          0%, 100% { background: #f9fafb; border-color: #d1d5db; box-shadow: none; }
          25%, 75% { background: #eef2ff; border-color: #1a3a6b; box-shadow: 0 0 0 3px rgba(26,58,107,0.15); }
        }
        .verifai-tooltip { position: relative; display: inline-flex; align-items: center; }
        .verifai-tooltip .verifai-tooltip-text {
  visibility: hidden; opacity: 0; width: 260px; background: #1a3a6b; color: white;
  font-size: 12px; line-height: 1.5; border-radius: 8px; padding: 10px 12px;
  position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
  transition: opacity 0.15s; pointer-events: auto; z-index: 100;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.verifai-tooltip .verifai-tooltip-text::after {
  content: ''; position: absolute; top: 100%; left: 0; right: 0; height: 12px;
}
.verifai-tooltip:hover .verifai-tooltip-text { visibility: visible; opacity: 1; }
.verifai-tooltip .verifai-tooltip-text a { color: #93c5fd; text-decoration: underline; cursor: pointer; }
      `}</style>

      <div style={{ display: "flex", gap: "24px", maxWidth: "1200px", margin: "0 auto" }}>

        {/* Sidebar */}
        <div style={{ width: "280px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "16px" }}>

          {/* Credibility Score */}
          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0", textAlign: "center" }}>
            <div className="verifai-tooltip" style={{ display: "inline-flex", justifyContent: "center", alignItems: "center", gap: "6px", marginBottom: "16px", cursor: "default" }}>
              <p style={{ fontSize: "11px", fontWeight: "700", color: "#1a3a6b", letterSpacing: "1px", margin: 0 }}>CREDIBILITY SCORE</p>
              <span style={{ width: "15px", height: "15px", borderRadius: "50%", background: "#e8edf5", color: "#1a3a6b", fontSize: "9px", fontWeight: "700", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>?</span>
              <span className="verifai-tooltip-text" style={{ width: "240px", left: "50%", textAlign: "left" }}>
                <strong style={{ display: "block", marginBottom: "6px" }}>How is this calculated?</strong>
                Each verified claim is weighted by verdict:<br />
                Supported × 1.0 + Partially Supported × 0.5<br />
                divided by total claims × 100.<br /><br />
                <strong>≥ 80%</strong> — Reliable<br />
                <strong>50–79%</strong> — Partially Reliable<br />
                <strong>&lt; 50%</strong> — Low Reliability
              </span>
            </div>
            <div style={{ position: "relative", width: "120px", height: "120px", margin: "0 auto 12px" }}>
              <svg viewBox="0 0 120 120" width="120" height="120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#e0e0e0" strokeWidth="12"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke={credibilityColor} strokeWidth="12"
                  strokeDasharray={`${2 * Math.PI * 50 * (credibilityScore / 100)} ${2 * Math.PI * 50 * (1 - credibilityScore / 100)}`}
                  strokeLinecap="round" transform="rotate(-90 60 60)"/>
              </svg>
              <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", fontSize: "20px", fontWeight: "700", color: "#111" }}>{credibilityScore.toFixed(1)}%</div>
            </div>
            <p style={{ color: credibilityColor, fontWeight: "600", fontSize: "14px", marginBottom: "8px" }}>{credibilityLabel}</p>
            <p style={{ color: "#888", fontSize: "12px", lineHeight: "1.5" }}>
              {credibilityScore >= 80
                ? "The majority of claims are well-supported by their cited sources."
                : credibilityScore >= 50
                ? "Some claims are inaccurate or unsupported by their cited sources."
                : "A significant portion of claims could not be verified or are unsupported."}
            </p>
          </div>

          {/* Claims Summary */}
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
                <div key={item.label} style={{ width: totalClaims > 0 ? `${(item.count / totalClaims) * 100}%` : "0%", background: item.color }} />
              ))}
            </div>
          </div>

          {/* File */}
          <div style={{ background: "white", borderRadius: "12px", padding: "16px 24px", border: "1px solid #e0e0e0", display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ background: "#eef2ff", borderRadius: "8px", padding: "10px", fontSize: "20px", flexShrink: 0 }}>📄</div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <p title={fileName} style={{ fontSize: "14px", fontWeight: "600", color: "#111", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{fileName}</p>
              <p style={{ fontSize: "12px", color: "#888" }}>{totalClaims} claims processed</p>
            </div>
          </div>

          {/* View */}
          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "12px" }}>VIEW</p>
            <div style={{ display: "flex", border: "1px solid #1a3a6b", borderRadius: "8px", overflow: "hidden" }}>
              <button onClick={() => setActiveView('overview')} style={{ flex: 1, padding: "10px", border: "none", cursor: "pointer", fontSize: "14px", fontWeight: "700", background: activeView === 'overview' ? "#1a3a6b" : "white", color: activeView === 'overview' ? "white" : "#1a3a6b" }}>Overview</button>
              <button onClick={() => setActiveView('citation')} style={{ flex: 1, padding: "10px", border: "none", borderLeft: "1px solid #1a3a6b", cursor: "pointer", fontSize: "14px", fontWeight: "700", background: activeView === 'citation' ? "#1a3a6b" : "white", color: activeView === 'citation' ? "white" : "#1a3a6b" }}>Network Graph</button>
            </div>
          </div>

          {/* Export */}
          <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "12px" }}>EXPORT</p>
            <button onClick={handleDownload} style={{ width: "100%", background: "#1a3a6b", color: "white", border: "none", borderRadius: "8px", padding: "12px", cursor: "pointer", fontSize: "14px", fontWeight: "600" }}>Download PDF report</button>
          </div>

          {/* Unresolved */}
          {summaryItems[4].count > 0 && (
            <div style={{ background: "white", borderRadius: "12px", padding: "24px", border: "1px solid #e0e0e0" }}>
              <p style={{ fontSize: "12px", fontWeight: "700", color: "#111", letterSpacing: "1px", marginBottom: "8px" }}>UNRESOLVED SOURCES</p>
              <p style={{ fontSize: "12px", color: "#888", marginBottom: "14px", lineHeight: "1.5" }}>{summaryItems[4].count} claim(s) couldn't be checked automatically.</p>
              <button onClick={jumpToUnresolvedSources} style={{ width: "100%", background: "white", color: "#1a3a6b", border: "1px solid #1a3a6b", borderRadius: "8px", padding: "12px", cursor: "pointer", fontSize: "13px", fontWeight: "600" }}>
                Add reference documents to check claims
              </button>
            </div>
          )}

        </div>

        {/* Main */}
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <h2 style={{ fontSize: "24px", fontWeight: "700", color: "#111", margin: 0 }}>Verification Results</h2>
            <button onClick={() => navigate('/')} style={{ border: "1px solid #ccc", background: "white", borderRadius: "8px", padding: "8px 20px", cursor: "pointer", fontSize: "14px" }}>← New document</button>
          </div>
          <p style={{ color: "#888", fontSize: "14px", marginBottom: "20px" }}>
            {totalClaims} claims checked · {claims.filter(c => c.doiResolved).length} DOIs resolved · {claims.filter(c => !c.doiResolved).length} unresolvable
          </p>

          {activeView === 'overview' && (
            <>
              <div ref={claimsListRef} style={{ display: "flex", gap: "8px", marginBottom: "24px", flexWrap: "wrap" }}>
                {filters.map((filter) => (
                  <button key={filter.label} onClick={() => setActiveFilter(filter.label)} style={{ padding: "8px 16px", borderRadius: "99px", fontSize: "13px", fontWeight: "600", cursor: "pointer", background: activeFilter === filter.label ? filter.color : "white", color: activeFilter === filter.label ? "white" : filter.color, border: `1px solid ${filter.border}` }}>
                    {filter.label}
                  </button>
                ))}
              </div>
              {/* Sort bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '16px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: '#888', fontWeight: '600', marginRight: '2px' }}>Sort:</span>
                {[
                  { key: 'default', label: 'Default' },
                  { key: 'status', label: 'Status' },
                  { key: 'confidence', label: 'Confidence' },
                  { key: 'source', label: 'Source' },
                  { key: 'author', label: 'Author' },
                ].map(opt => (
                  <button
                    key={opt.key}
                    onClick={() => setSortBy(opt.key)}
                    style={{
                      padding: '5px 12px', borderRadius: '6px', fontSize: '12px', fontWeight: '600',
                      cursor: 'pointer', border: '1px solid',
                      background: sortBy === opt.key ? '#1a3a6b' : 'white',
                      color: sortBy === opt.key ? 'white' : '#555',
                      borderColor: sortBy === opt.key ? '#1a3a6b' : '#ddd',
                      transition: 'all 0.15s',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {filteredClaims.length === 0 ? (
                <p style={{ color: "#888", fontSize: "14px", textAlign: "center", padding: "40px 0" }}>No claims match this filter.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  {filteredClaims.map(claim => {
                    const config = statusConfig[claim.status]
                    const showManualUpload = !claim.doiResolved || claim.status === 'insufficient'
                    const uploadState = refUploadStatus[claim.id]
                    const similarityHint = claim.status === 'insufficient' ? getSimilarityHint(claim.similarityScore) : null
                    const evidenceHint = getEvidenceAvailabilityHint(claim.evidenceAvailability, claim.status)
                    const doiExplanation = getDoiStatusExplanation(claim.doiStatus, claim.evidenceAvailability)
                    const isPassageOpen = expandedPassages[claim.id]
                    const isReasoningExpanded = expandedReasoning[claim.id]
                    const reasoningIsLong = claim.reasoning.length > 120

                    return (
                      <div key={claim.id} style={{ background: "white", borderRadius: "12px", padding: "24px", border: `1px solid ${config.border}` }}>

                        {/* Header */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                          <span style={{ fontSize: "12px", fontWeight: "700", color: "#888", letterSpacing: "1px" }}>CLAIM {claim.displayId}</span>
                          <div className="verifai-tooltip">
                            <span style={{ fontSize: "12px", fontWeight: "700", color: config.color, background: config.bg, padding: "4px 12px", borderRadius: "99px", border: `1px solid ${config.border}`, cursor: "default" }}>
                              {config.label}
                            </span>
                            <span className="verifai-tooltip-text" style={{ textAlign: "left" }}>
                              {STATUS_TOOLTIPS[claim.status]}
                              {' '}
<a href={`/how-it-works?tab=categories#category-${STATUS_ANCHOR[claim.status]}`} style={{ color: "#93c5fd", fontSize: "11px", display: "block", marginTop: "6px" }} onClick={e => e.stopPropagation()}>
  Learn more
</a>
                            </span>
                          </div>
                        </div>

                        <p style={{ fontSize: "14px", color: "#333", marginBottom: "16px", lineHeight: "1.6" }}>{claim.text}</p>

                        <p style={{ fontSize: "13px", color: "#666", marginBottom: claim.authorLine ? "4px" : "8px", fontStyle: "italic" }}>{claim.source}</p>
                        {claim.authorLine && <p style={{ fontSize: "12px", color: "#999", marginBottom: "8px" }}>{claim.authorLine}</p>}

                        <div style={{ display: "flex", gap: "8px", marginBottom: doiExplanation ? "6px" : "16px", flexWrap: "wrap" }}>
                          <span style={{ fontSize: "12px", color: "#555", background: "#f5f5f5", padding: "4px 12px", borderRadius: "99px", border: "1px solid #e0e0e0" }}>
                            {claim.doiResolved ? "✓ DOI resolved" : "✗ DOI unresolved"}
                          </span>
                        </div>
                        {doiExplanation && <p style={{ fontSize: "12px", color: doiExplanation.color, marginBottom: "16px", lineHeight: "1.5" }}>{doiExplanation.text}</p>}

                        {/* AI Reasoning collapsible */}
                        <div style={{ background: "#f8f8f8", borderRadius: "8px", padding: "16px", marginBottom: evidenceHint || similarityHint || claim.warning ? "12px" : "16px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                            <p style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "1px", margin: 0 }}>AI REASONING</p>
                            {reasoningIsLong && (
                              <button onClick={() => setExpandedReasoning(prev => ({ ...prev, [claim.id]: !prev[claim.id] }))} style={{ fontSize: "11px", color: "#1a3a6b", background: "none", border: "none", cursor: "pointer", fontWeight: "600", padding: 0, flexShrink: 0 }}>
                                {isReasoningExpanded ? "Show less" : "Show more"}
                              </button>
                            )}
                          </div>
                          <p style={{ fontSize: "13px", color: "#444", lineHeight: "1.6", margin: 0, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: isReasoningExpanded ? 999 : 2, WebkitBoxOrient: "vertical" }}>
                            {claim.reasoning}
                          </p>
                        </div>

                        {evidenceHint && (
                          <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                            <p style={{ fontSize: "13px", fontWeight: "600", color: "#1d4ed8", marginBottom: "4px" }}>i {evidenceHint.label}</p>
                            <p style={{ fontSize: "12px", color: "#3b82f6", lineHeight: "1.5" }}>{evidenceHint.detail}</p>
                          </div>
                        )}

                        {similarityHint && (
                          <div style={{ background: "#f3f4f6", border: "1px solid #d1d5db", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                            <p style={{ fontSize: "13px", fontWeight: "600", color: "#4b5563", marginBottom: "4px" }}>! {similarityHint.label}</p>
                            <p style={{ fontSize: "12px", color: "#6b7280", lineHeight: "1.5" }}>{similarityHint.detail}</p>
                          </div>
                        )}

                        {claim.warning && (
                          <div style={{ background: "#fffbeb", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                            <p style={{ fontSize: "13px", color: "#d97706", lineHeight: "1.5" }}>{claim.warning}</p>
                            <p style={{ fontSize: "13px", color: "#d97706", lineHeight: "1.6", marginTop: "6px" }}>{getHumanReviewReason(claim.doiStatus, claim.evidenceAvailability)}</p>
                          </div>
                        )}

                        {showManualUpload && (
                          <div style={{ background: "#f9fafb", border: "1px dashed #d1d5db", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", animation: flashUpload ? "verifai-flash-highlight 0.6s ease-in-out 2" : "none" }}>
                            {uploadState === 'checking' ? (
                              <p style={{ fontSize: "13px", color: "#1a3a6b", display: "flex", alignItems: "center", gap: "2px" }}>
                                Re-checking this claim automatically
                                <span style={{ display: "inline-flex", gap: "2px", marginLeft: "4px" }}>
                                  {[0, 0.2, 0.4].map(d => <span key={d} style={{ width: "4px", height: "4px", borderRadius: "50%", background: "#1a3a6b", animation: "verifai-dot-pulse 1.2s infinite", animationDelay: `${d}s` }} />)}
                                </span>
                              </p>
                            ) : (
                              <>
                                <input type="file" accept=".pdf" id={`ref-upload-${claim.id}`} style={{ display: "none" }} onChange={(e) => { const file = e.target.files[0]; if (file) handleManualReferenceUpload(claim, file) }} />
                                <button type="button" onClick={() => document.getElementById(`ref-upload-${claim.id}`).click()} disabled={uploadState === 'uploading'} style={{ fontSize: "13px", color: "#1a3a6b", background: "none", border: "none", cursor: "pointer", fontWeight: "600", padding: 0, display: "flex", alignItems: "center", gap: "6px" }}>
                                  {uploadState === 'uploading' ? (<><span style={{ width: "12px", height: "12px", borderRadius: "50%", border: "2px solid #c5cfe0", borderTopColor: "#1a3a6b", animation: "verifai-step-spin 0.8s linear infinite", display: "inline-block" }} />Uploading...</>) : "Add the reference manually"}
                                </button>
                                <p style={{ fontSize: "11px", color: "#aaa", marginTop: "6px" }}>PDF only, max. 50 MB</p>
                                {uploadState === 'error' && <p style={{ fontSize: "12px", color: "#dc2626", marginTop: "6px" }}>{refUploadError[claim.id] || "Upload failed, please try again."}</p>}
                                {uploadState === 'no-reference' && <p style={{ fontSize: "12px", color: "#dc2626", marginTop: "6px" }}>This claim has no linked reference ID - manual upload isn't possible here.</p>}
                              </>
                            )}
                          </div>
                        )}

                        {/* Footer */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div className="verifai-tooltip" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{ fontSize: "12px", color: "#888" }}>Confidence</span>
                            <div style={{ width: "80px", height: "6px", background: "#e0e0e0", borderRadius: "99px", overflow: "hidden" }}>
                              <div style={{ width: `${claim.confidence * 100}%`, height: "6px", background: getConfidenceColor(claim.confidence), borderRadius: "99px" }} />
                            </div>
                            <span style={{ fontSize: "12px", color: "#888" }}>{(claim.confidence * 100).toFixed(1)}%</span>
                            <span style={{ width: "14px", height: "14px", borderRadius: "50%", background: "#e8edf5", color: "#1a3a6b", fontSize: "9px", fontWeight: "700", display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "default", flexShrink: 0 }}>?</span>
                            <span className="verifai-tooltip-text">{CONFIDENCE_TOOLTIP}</span>
                          </div>
                          <button
                            style={{ fontSize: "12px", color: "#1a3a6b", background: "none", border: "none", cursor: "pointer", fontWeight: "600" }}
                            onClick={async () => {
                              const isOpen = expandedPassages[claim.id]
                              setExpandedPassages(prev => ({ ...prev, [claim.id]: !isOpen }))
                              if (!isOpen && !passageData[claim.id]) {
                                try {
                                  const detail = await getVerificationResult(claim.id)
                                  let chunks = (detail.retrieved_evidence ?? []).flatMap(r => r.top_chunks ?? [r])
                                  if (chunks.length === 0 && detail.explanation) {
                                    const match = detail.explanation.match(/Reused cached verification result (result_[a-z0-9]+)/)
                                    if (match && match[1] !== claim.id) {
                                      try {
                                        const original = await getVerificationResult(match[1])
                                        chunks = (original.retrieved_evidence ?? []).flatMap(r => r.top_chunks ?? [r])
                                      } catch { /* leave empty */ }
                                    }
                                  }
                                  const seen = new Set()
                                  chunks = chunks.filter(c => { const key = c.chunk_id ?? c.chunk_text; if (seen.has(key)) return false; seen.add(key); return true })
                                  setPassageData(prev => ({ ...prev, [claim.id]: chunks }))
                                } catch {
                                  setPassageData(prev => ({ ...prev, [claim.id]: [] }))
                                }
                              }
                            }}
                          >
                            {isPassageOpen ? 'Hide source passage' : 'Show source passage'}
                          </button>
                        </div>

                        {/* Source passage */}
                        {isPassageOpen && (
                          <div style={{ marginTop: "16px", borderTop: "1px solid #e0e0e0", paddingTop: "16px" }}>
                            <p style={{ fontSize: "11px", fontWeight: "700", color: "#888", letterSpacing: "1px", marginBottom: "12px" }}>SOURCE PASSAGES USED</p>
                            {passageData[claim.id] === undefined ? (
                              <p style={{ fontSize: "13px", color: "#888" }}>Loading...</p>
                            ) : passageData[claim.id].length === 0 ? (
                              <p style={{ fontSize: "13px", color: "#888" }}>No source passages were retrieved for this claim.</p>
                            ) : (
                              passageData[claim.id].map((chunk, i) => (
                                <div key={i} style={{ background: "#f8f8f8", borderRadius: "8px", padding: "12px 16px", marginBottom: "10px", borderLeft: "3px solid #1a3a6b" }}>
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                                    <span style={{ fontSize: "11px", fontWeight: "700", color: "#1a3a6b", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                                      {chunk.section ?? chunk.evidence_type ?? 'Passage'}{chunk.similarity_score != null ? ` · ${(chunk.similarity_score * 100).toFixed(1)}% match` : ''}
                                    </span>
                                    {chunk.source_url && (
                                      <a href={chunk.source_url} target="_blank" rel="noreferrer" style={{ fontSize: "11px", color: "#1a3a6b" }}>Open PDF</a>
                                    )}
                                  </div>
                                  <p style={{ fontSize: "13px", color: "#444", lineHeight: "1.6", margin: 0 }}>{chunk.chunk_text ?? chunk.text}</p>
                                </div>
                              ))
                            )}
                          </div>
                        )}

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
                  <button key={filter.key} onClick={() => setCitationFilter(filter.key)} style={{ padding: "8px 16px", borderRadius: "99px", fontSize: "13px", fontWeight: "600", cursor: "pointer", background: citationFilter === filter.key ? filter.color : "white", color: citationFilter === filter.key ? "white" : filter.color, border: `1px solid ${filter.border}` }}>
                    {filter.label}
                  </button>
                ))}
              </div>
<CitationGraph
  claims={claims}
  statusConfig={statusConfig}
  documentLabel={fileName}
  statusFilter={citationFilter}
  onManualUpload={handleManualReferenceUpload}
  flashUpload={flashUpload}
  refUploadStatus={refUploadStatus}
  refUploadError={refUploadError}
/>            </>
          )}

          {/* Legend */}
          <div style={{ marginTop: "40px", paddingTop: "24px", borderTop: "1px solid #e0e0e0" }}>
            <p style={{ fontSize: "12px", fontWeight: "700", color: "#888", letterSpacing: "1px", marginBottom: "16px" }}>UNDERSTANDING THESE RESULTS</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "16px" }}>
              {Object.entries(statusConfig).map(([key, item]) => (
                <div key={item.label} className="verifai-tooltip" style={{ display: "flex", alignItems: "center", gap: "8px", background: item.bg, border: `1px solid ${item.border}`, borderRadius: "8px", padding: "8px 14px" }}>
                  <span style={{ width: "10px", height: "10px", borderRadius: "50%", background: item.color, flexShrink: 0 }} />
                  <span style={{ fontSize: "13px", color: "#333" }}>{item.label}</span>
                  <span className="verifai-tooltip-text">{STATUS_TOOLTIPS[key]}</span>
                </div>
              ))}
            </div>
            <p style={{ fontSize: "13px", color: "#888", lineHeight: "1.6" }}>
              Not sure how a verdict is determined, or why some sources can't be checked automatically?{' '}
              <a href="/how-it-works" style={{ color: "#1a3a6b", fontWeight: "600", textDecoration: "underline" }}>See how VerifAi works</a>
            </p>
          </div>

        </div>
      </div>
    </div>
  )
}

export default ResultsPage