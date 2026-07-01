import { useState, useMemo } from 'react'

const HUB_R = 20
const SOURCE_R = 9
const CLAIM_R = 7
const RING_1 = 150
const RING_2 = 300
const MAX_LABEL_CHARS = 26

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

function truncate(text, maxLen = MAX_LABEL_CHARS) {
  if (!text) return text
  return text.length > maxLen ? text.slice(0, maxLen - 1).trimEnd() + '…' : text
}

function buildRadialLayout(allClaims) {
  const bySource = new Map()
  allClaims.forEach((claim) => {
    const key = claim.source || 'Unknown source'
    if (!bySource.has(key)) bySource.set(key, [])
    bySource.get(key).push(claim)
  })

  const sourceEntries = Array.from(bySource.entries())
  const total = sourceEntries.length || 1
  const cx = 500
  const cy = 400

  const sourceNodes = []
  const claimNodes = []

  sourceEntries.forEach(([source, sourceClaims], i) => {
    const angle = (i / total) * 2 * Math.PI - Math.PI / 2
    const sx = cx + RING_1 * Math.cos(angle)
    const sy = cy + RING_1 * Math.sin(angle)
    const flagged = sourceClaims.filter(
      (c) => c.status === 'hallucinated' || c.status === 'unsupported'
    ).length
    // Pick DOI URL from first claim that has one
    const doiUrl = sourceClaims.find(c => c.doiUrl)?.doiUrl ?? null
    sourceNodes.push({ id: source, label: source, x: sx, y: sy, angle, flagged, count: sourceClaims.length, doiUrl })

    const maxSpread = Math.min(0.32, (Math.PI / total) * 0.7)
    sourceClaims.forEach((claim, j) => {
      const n = sourceClaims.length
      const spread = n > 1 ? (j - (n - 1) / 2) * (maxSpread / Math.max(n - 1, 1)) * 2 : 0
      const claimAngle = angle + spread
      const ringOffset = n > 1 && j % 2 === 1 ? 30 : 0
      const r = RING_2 + ringOffset
      const cx2 = cx + r * Math.cos(claimAngle)
      const cy2 = cy + r * Math.sin(claimAngle)
      claimNodes.push({ ...claim, x: cx2, y: cy2, angle: claimAngle, sourceX: sx, sourceY: sy, sourceId: source })
    })
  })

  return { cx, cy, sourceNodes, claimNodes }
}

export default function CitationGraph({ claims, statusConfig, documentLabel = 'This paper', statusFilter = 'all', onManualUpload, flashUpload, refUploadStatus, refUploadError }) {
  const [activeClaimId, setActiveClaimId] = useState(null)
  const [activeSourceId, setActiveSourceId] = useState(null)
  const [expandedReasoning, setExpandedReasoning] = useState({})

  const allClaims = useMemo(() => claims, [claims])
  const { cx, cy, sourceNodes, claimNodes } = useMemo(() => buildRadialLayout(allClaims), [allClaims])

  const activeClaim = allClaims.find((c) => c.id === activeClaimId)
  const activeSource = sourceNodes.find((s) => s.id === activeSourceId)
  const highlighted = statusFilter !== 'all' ? statusFilter : null

  const getConfidenceColor = (c) => c > 0.7 ? "#16a34a" : c > 0.4 ? "#d97706" : "#dc2626"

  // Claims filtered by active source
  const sourceFilteredClaims = activeSourceId
    ? claimNodes.filter(c => c.sourceId === activeSourceId)
    : []

  if (allClaims.length === 0) {
    return (
      <div style={{ background: 'white', borderRadius: '12px', padding: '40px 24px', border: '1px solid #e0e0e0', textAlign: 'center' }}>
        <p style={{ color: '#888', fontSize: '14px' }}>No claims to display yet.</p>
      </div>
    )
  }

  return (
    <div style={{ background: 'white', borderRadius: '12px', padding: '24px', border: '1px solid #e0e0e0' }}>
      <style>{`
        @keyframes verifai-dot-pulse { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }
        @keyframes verifai-step-spin { to { transform: rotate(360deg); } }
        @keyframes verifai-flash-highlight {
          0%, 100% { background: #f9fafb; border-color: #d1d5db; box-shadow: none; }
          25%, 75% { background: #eef2ff; border-color: #1a3a6b; box-shadow: 0 0 0 3px rgba(26,58,107,0.15); }
        }
        .graph-tooltip { position: relative; display: inline-flex; align-items: center; }
        .graph-tooltip .graph-tooltip-text {
          visibility: hidden; opacity: 0; width: 240px; background: #1a3a6b; color: white;
          font-size: 12px; line-height: 1.5; border-radius: 8px; padding: 10px 12px;
          position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
          transition: opacity 0.15s; pointer-events: auto; z-index: 100;
          box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .graph-tooltip:hover .graph-tooltip-text { visibility: visible; opacity: 1; }
        .graph-tooltip .graph-tooltip-text a { color: #93c5fd; text-decoration: underline; }
      `}</style>

      <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111', margin: 0 }}>Citation Network Graph</h3>
      <p style={{ color: '#888', fontSize: '13px', margin: '4px 0 16px 0' }}>
        Click a <strong>source node</strong> (○) to filter its claims. Click a <strong>claim dot</strong> (●) to see details.
      </p>

      {/* Active source banner */}
      {activeSource && (
        <div style={{ background: '#eef2ff', border: '1px solid #c5cfe0', borderRadius: '8px', padding: '10px 16px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontSize: '12px', fontWeight: '700', color: '#1a3a6b' }}>Showing claims from: </span>
            <span style={{ fontSize: '13px', color: '#333' }}>{activeSource.label}</span>
            {activeSource.doiUrl && (
              <a href={activeSource.doiUrl} target="_blank" rel="noreferrer"
                style={{ fontSize: '12px', color: '#1a3a6b', marginLeft: '12px', textDecoration: 'underline' }}>
                Open paper ↗
              </a>
            )}
          </div>
          <button onClick={() => { setActiveSourceId(null); setActiveClaimId(null) }}
            style={{ border: 'none', background: 'none', fontSize: '16px', cursor: 'pointer', color: '#888' }}>×</button>
        </div>
      )}

      <div style={{ border: '1px solid #e0e0e0', borderRadius: '8px', background: '#fafafa', padding: '12px', overflowX: 'auto' }}>
        <svg width="100%" viewBox="0 0 1000 800" style={{ display: 'block', minWidth: '700px' }}>

          {sourceNodes.map((s) => {
            const sourceHasMatch = highlighted && claimNodes.some((c) => c.sourceId === s.id && c.status === highlighted)
            const isActiveSource = activeSourceId === s.id
            const dimmed = (highlighted && !sourceHasMatch) || (activeSourceId && !isActiveSource)
            return (
              <line key={`hub-${s.id}`} x1={cx} y1={cy} x2={s.x} y2={s.y}
                stroke={isActiveSource || (highlighted && sourceHasMatch) ? '#1a3a6b' : '#d6d3cd'}
                strokeWidth={isActiveSource ? 3 : (highlighted && sourceHasMatch) ? 2.5 : 1}
                opacity={dimmed ? 0.25 : 1}
              />
            )
          })}

          {claimNodes.map((c) => {
            const matched = highlighted && c.status === highlighted
            const isSourceMatch = activeSourceId && c.sourceId === activeSourceId
            const dimmed = (highlighted && !matched) || (activeSourceId && !isSourceMatch)
            return (
              <line key={`edge-${c.id}`} x1={c.sourceX} y1={c.sourceY} x2={c.x} y2={c.y}
                stroke={matched || isSourceMatch ? '#1a3a6b' : '#d6d3cd'}
                strokeWidth={matched || isSourceMatch ? 2.5 : 1}
                opacity={dimmed ? 0.25 : 1}
              />
            )
          })}

          <circle cx={cx} cy={cy} r={HUB_R} fill="#1a3a6b" />
          <text x={cx} y={cy + 4} textAnchor="middle" fontSize="10" fontWeight="600" fill="#fff">doc</text>
          <text x={cx} y={cy - HUB_R - 12} textAnchor="middle" fontSize="11" fontWeight="700" fill="#1a3a6b">
            {truncate(documentLabel, 34)}
          </text>

          {sourceNodes.map((s) => {
            const sourceHasMatch = highlighted && claimNodes.some((c) => c.sourceId === s.id && c.status === highlighted)
            const isActiveSource = activeSourceId === s.id
            const dimmed = (highlighted && !sourceHasMatch) || (activeSourceId && !isActiveSource)
            const isNearHorizontal = Math.abs(Math.sin(s.angle)) < 0.5
            const labelY = isNearHorizontal ? s.y + SOURCE_R + 16 : s.y - SOURCE_R - 18
            const subLabelY = labelY + 14
            return (
              <g key={s.id} opacity={dimmed ? 0.35 : 1}
                onClick={() => {
                  setActiveClaimId(null)
                  setActiveSourceId(activeSourceId === s.id ? null : s.id)
                }}
                style={{ cursor: 'pointer' }}
              >
                <circle cx={s.x} cy={s.y} r={isActiveSource ? SOURCE_R + 2 : SOURCE_R}
                  fill={isActiveSource ? '#eef2ff' : 'white'}
                  stroke="#1a3a6b" strokeWidth={isActiveSource ? 2.5 : 1.5} />
                <text x={s.x} y={labelY} textAnchor="middle" fontSize="11" fontWeight="700" fill="#111">{truncate(s.label)}</text>
                <text x={s.x} y={subLabelY} textAnchor="middle" fontSize="9.5" fill="#888">
                  {s.count} claim{s.count > 1 ? 's' : ''}{s.flagged > 0 ? ` · ${s.flagged} flagged` : ''}
                </text>
              </g>
            )
          })}

          {claimNodes.map((c) => {
            const cfg = statusConfig[c.status]
            const isActive = activeClaimId === c.id
            const matched = highlighted && c.status === highlighted
            const isSourceMatch = activeSourceId && c.sourceId === activeSourceId
            const dimmed = (highlighted && !matched) || (activeSourceId && !isSourceMatch)
            return (
              <g key={c.id}
                onClick={() => {
                  setActiveSourceId(null)
                  setActiveClaimId(isActive ? null : c.id)
                }}
                style={{ cursor: 'pointer' }} opacity={dimmed ? 0.25 : 1}
              >
                <circle cx={c.x} cy={c.y}
                  r={isActive || matched ? CLAIM_R + 1.5 : CLAIM_R}
                  fill={cfg.color} stroke="white" strokeWidth="1.5"
                />
              </g>
            )
          })}
        </svg>
      </div>

      {/* Source: list all its claims */}
      {activeSourceId && !activeClaimId && sourceFilteredClaims.length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <p style={{ fontSize: '12px', fontWeight: '700', color: '#888', letterSpacing: '1px', marginBottom: '12px' }}>
            CLAIMS FROM THIS SOURCE ({sourceFilteredClaims.length})
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {sourceFilteredClaims.map(claim => {
              const cfg = statusConfig[claim.status]
              return (
                <div key={claim.id}
                  onClick={() => setActiveClaimId(claim.id)}
                  style={{ background: '#f8f8f8', borderRadius: '8px', padding: '12px 16px', cursor: 'pointer', border: `1px solid ${cfg.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                  <p style={{ fontSize: '13px', color: '#333', lineHeight: '1.5', margin: 0, flex: 1 }}>{claim.text}</p>
                  <span style={{ fontSize: '11px', fontWeight: '700', color: cfg.color, background: cfg.bg, padding: '3px 10px', borderRadius: '99px', border: `1px solid ${cfg.border}`, flexShrink: 0 }}>
                    {cfg.label}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Full claim card */}
      {activeClaim && (() => {
        const config = statusConfig[activeClaim.status]
        const uploadState = refUploadStatus?.[activeClaim.id]
        const showManualUpload = !activeClaim.doiResolved || activeClaim.status === 'insufficient'
        const isReasoningExpanded = expandedReasoning[activeClaim.id]
        const reasoningIsLong = activeClaim.reasoning?.length > 120

        return (
          <div style={{ marginTop: '20px', background: 'white', borderRadius: '12px', padding: '24px', border: `1px solid ${config.border}` }}>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '12px', fontWeight: '700', color: '#888', letterSpacing: '1px' }}>
                CLAIM {activeClaim.displayId ?? activeClaim.id}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div className="graph-tooltip">
                  <span style={{ fontSize: '12px', fontWeight: '700', color: config.color, background: config.bg, padding: '4px 12px', borderRadius: '99px', border: `1px solid ${config.border}`, cursor: 'default' }}>
                    {config.label} <span style={{ opacity: 0.6, fontSize: '10px' }}>i</span>
                  </span>
                  <span className="graph-tooltip-text" style={{ textAlign: 'left' }}>
                    {STATUS_TOOLTIPS[activeClaim.status]}{' '}
                    <a href={`/how-it-works?tab=categories#category-${STATUS_ANCHOR[activeClaim.status]}`}
                      style={{ color: '#93c5fd', fontSize: '11px', display: 'block', marginTop: '6px' }}
                      onClick={e => e.stopPropagation()}>
                      Learn more
                    </a>
                  </span>
                </div>
                <button onClick={() => setActiveClaimId(null)}
                  style={{ border: 'none', background: 'none', fontSize: '18px', cursor: 'pointer', color: '#888', lineHeight: 1 }}>×</button>
              </div>
            </div>

            <p style={{ fontSize: '14px', color: '#333', marginBottom: '16px', lineHeight: '1.6' }}>{activeClaim.text}</p>

            <p style={{ fontSize: '13px', color: '#666', marginBottom: activeClaim.authorLine ? '4px' : '8px', fontStyle: 'italic' }}>{activeClaim.source}</p>
            {activeClaim.authorLine && <p style={{ fontSize: '12px', color: '#999', marginBottom: '8px' }}>{activeClaim.authorLine}</p>}

            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '12px', color: '#555', background: '#f5f5f5', padding: '4px 12px', borderRadius: '99px', border: '1px solid #e0e0e0' }}>
                {activeClaim.doiResolved ? '✓ DOI resolved' : '✗ DOI unresolved'}
              </span>
              {activeClaim.doiUrl && (
                <a href={activeClaim.doiUrl} target="_blank" rel="noreferrer"
                  style={{ fontSize: '12px', color: '#1a3a6b', background: '#eef2ff', padding: '4px 12px', borderRadius: '99px', border: '1px solid #c5cfe0', textDecoration: 'none' }}>
                  Open paper ↗
                </a>
              )}
            </div>

            <div style={{ background: '#f8f8f8', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <p style={{ fontSize: '11px', fontWeight: '700', color: '#888', letterSpacing: '1px', margin: 0 }}>AI REASONING</p>
                {reasoningIsLong && (
                  <button onClick={() => setExpandedReasoning(prev => ({ ...prev, [activeClaim.id]: !prev[activeClaim.id] }))}
                    style={{ fontSize: '11px', color: '#1a3a6b', background: 'none', border: 'none', cursor: 'pointer', fontWeight: '600', padding: 0 }}>
                    {isReasoningExpanded ? 'Show less' : 'Show more'}
                  </button>
                )}
              </div>
              <p style={{ fontSize: '13px', color: '#444', lineHeight: '1.6', margin: 0, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: isReasoningExpanded ? 999 : 2, WebkitBoxOrient: 'vertical' }}>
                {activeClaim.reasoning}
              </p>
            </div>

            {activeClaim.warning && (
              <div style={{ background: '#fffbeb', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px' }}>
                <p style={{ fontSize: '13px', color: '#d97706', lineHeight: '1.5', margin: 0 }}>{activeClaim.warning}</p>
              </div>
            )}

            {showManualUpload && onManualUpload && (
              <div style={{ background: '#f9fafb', border: '1px dashed #d1d5db', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px', animation: flashUpload ? 'verifai-flash-highlight 0.6s ease-in-out 2' : 'none' }}>
                {uploadState === 'checking' ? (
                  <p style={{ fontSize: '13px', color: '#1a3a6b', display: 'flex', alignItems: 'center', gap: '2px' }}>
                    Re-checking this claim automatically
                    <span style={{ display: 'inline-flex', gap: '2px', marginLeft: '4px' }}>
                      {[0, 0.2, 0.4].map(d => <span key={d} style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#1a3a6b', animation: 'verifai-dot-pulse 1.2s infinite', animationDelay: `${d}s` }} />)}
                    </span>
                  </p>
                ) : (
                  <>
                    <input type="file" accept=".pdf" id={`graph-ref-upload-${activeClaim.id}`} style={{ display: 'none' }}
                      onChange={(e) => { const file = e.target.files[0]; if (file) onManualUpload(activeClaim, file) }} />
                    <button type="button"
                      onClick={() => document.getElementById(`graph-ref-upload-${activeClaim.id}`).click()}
                      disabled={uploadState === 'uploading'}
                      style={{ fontSize: '13px', color: '#1a3a6b', background: 'none', border: 'none', cursor: 'pointer', fontWeight: '600', padding: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {uploadState === 'uploading' ? (
                        <><span style={{ width: '12px', height: '12px', borderRadius: '50%', border: '2px solid #c5cfe0', borderTopColor: '#1a3a6b', animation: 'verifai-step-spin 0.8s linear infinite', display: 'inline-block' }} />Uploading...</>
                      ) : 'Add the reference manually'}
                    </button>
                    <p style={{ fontSize: '11px', color: '#aaa', marginTop: '6px' }}>PDF only, max. 50 MB</p>
                    {uploadState === 'error' && <p style={{ fontSize: '12px', color: '#dc2626', marginTop: '6px' }}>{refUploadError?.[activeClaim.id] || 'Upload failed, please try again.'}</p>}
                  </>
                )}
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '12px', color: '#888' }}>Confidence</span>
              <div style={{ width: '80px', height: '6px', background: '#e0e0e0', borderRadius: '99px', overflow: 'hidden' }}>
                <div style={{ width: `${activeClaim.confidence * 100}%`, height: '6px', background: getConfidenceColor(activeClaim.confidence), borderRadius: '99px' }} />
              </div>
              <span style={{ fontSize: '12px', color: '#888' }}>{(activeClaim.confidence * 100).toFixed(1)}%</span>
            </div>

          </div>
        )
      })()}
    </div>
  )
}