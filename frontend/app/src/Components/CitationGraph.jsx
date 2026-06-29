import { useState, useMemo } from 'react'

const HUB_R = 20
const SOURCE_R = 9
const CLAIM_R = 7
const RING_1 = 150
const RING_2 = 300
const MAX_LABEL_CHARS = 26

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

    sourceNodes.push({ id: source, label: source, x: sx, y: sy, angle, flagged, count: sourceClaims.length })

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

export default function CitationGraph({ claims, statusConfig, documentLabel = 'This paper', statusFilter = 'all' }) {
  const [activeId, setActiveId] = useState(null)

  const allClaims = useMemo(() => claims, [claims])
  const { cx, cy, sourceNodes, claimNodes } = useMemo(() => buildRadialLayout(allClaims), [allClaims])
  const active = allClaims.find((c) => c.id === activeId)
  const highlighted = statusFilter !== 'all' ? statusFilter : null

  if (allClaims.length === 0) {
    return (
      <div
        style={{
          background: 'white',
          borderRadius: '12px',
          padding: '40px 24px',
          border: '1px solid #e0e0e0',
          textAlign: 'center',
        }}
      >
        <p style={{ color: '#888', fontSize: '14px' }}>No claims to display yet.</p>
      </div>
    )
  }

  return (
    <div
      style={{
        background: 'white',
        borderRadius: '12px',
        padding: '24px',
        border: '1px solid #e0e0e0',
      }}
    >
      <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111', margin: 0 }}>
        Citation Network Graph
      </h3>
      <p style={{ color: '#888', fontSize: '13px', margin: '4px 0 16px 0' }}>
        Sources connected to the claims that cite them
      </p>

      <div
        style={{
          border: '1px solid #e0e0e0',
          borderRadius: '8px',
          background: '#fafafa',
          padding: '12px',
          overflowX: 'auto',
        }}
      >
        <svg width="100%" viewBox="0 0 1000 800" style={{ display: 'block', minWidth: '700px' }}>
          {sourceNodes.map((s) => {
            const sourceHasMatch = highlighted && claimNodes.some((c) => c.sourceId === s.id && c.status === highlighted)
            const bold = !highlighted || sourceHasMatch
            return (
              <line
                key={`hub-${s.id}`}
                x1={cx}
                y1={cy}
                x2={s.x}
                y2={s.y}
                stroke={highlighted && sourceHasMatch ? '#1a3a6b' : '#d6d3cd'}
                strokeWidth={highlighted && sourceHasMatch ? 2.5 : 1}
                opacity={bold ? 1 : 0.25}
              />
            )
          })}

          {claimNodes.map((c) => {
            const matched = highlighted && c.status === highlighted
            const dimmed = highlighted && !matched
            return (
              <line
                key={`edge-${c.id}`}
                x1={c.sourceX}
                y1={c.sourceY}
                x2={c.x}
                y2={c.y}
                stroke={matched ? '#1a3a6b' : '#d6d3cd'}
                strokeWidth={matched ? 2.5 : 1}
                opacity={dimmed ? 0.25 : 1}
              />
            )
          })}

          <circle cx={cx} cy={cy} r={HUB_R} fill="#1a3a6b" />
          <text x={cx} y={cy + 4} textAnchor="middle" fontSize="10" fontWeight="600" fill="#fff">
            doc
          </text>
          <text x={cx} y={cy - HUB_R - 12} textAnchor="middle" fontSize="11" fontWeight="700" fill="#1a3a6b">
            {truncate(documentLabel, 34)}
          </text>

          {sourceNodes.map((s) => {
            const sourceHasMatch = highlighted && claimNodes.some((c) => c.sourceId === s.id && c.status === highlighted)
            const dimmed = highlighted && !sourceHasMatch

            // Sources roughly level with the hub (near-horizontal angle) would
            // have their "above" label collide with the document title row
            // sitting directly above the hub. Push those labels below the
            // node instead; vertical-ish sources keep the label above.
            const isNearHorizontal = Math.abs(Math.sin(s.angle)) < 0.5
            const labelY = isNearHorizontal
              ? s.y + SOURCE_R + 16
              : s.y - SOURCE_R - 18
            const subLabelY = isNearHorizontal ? labelY + 14 : labelY + 14

            return (
              <g key={s.id} opacity={dimmed ? 0.35 : 1}>
                <circle cx={s.x} cy={s.y} r={SOURCE_R} fill="white" stroke="#1a3a6b" strokeWidth="1.5" />
                <text x={s.x} y={labelY} textAnchor="middle" fontSize="11" fontWeight="700" fill="#111">
                  {truncate(s.label)}
                </text>
                <text x={s.x} y={subLabelY} textAnchor="middle" fontSize="9.5" fill="#888">
                  {s.count} claim{s.count > 1 ? 's' : ''}{s.flagged > 0 ? ` · ${s.flagged} flagged` : ''}
                </text>
              </g>
            )
          })}

          {claimNodes.map((c) => {
            const cfg = statusConfig[c.status]
            const isActive = activeId === c.id
            const matched = highlighted && c.status === highlighted
            const dimmed = highlighted && !matched
            const labelY = c.y + CLAIM_R + 16
            return (
              <g key={c.id} onClick={() => setActiveId(isActive ? null : c.id)} style={{ cursor: 'pointer' }} opacity={dimmed ? 0.25 : 1}>
                <circle
                  cx={c.x}
                  cy={c.y}
                  r={isActive || matched ? CLAIM_R + 1.5 : CLAIM_R}
                  fill={cfg.color}
                  stroke="white"
                  strokeWidth="1.5"
                />
                {matched && (
                  <text x={c.x} y={labelY} textAnchor="middle" fontSize="10" fill={cfg.color} fontWeight="700">
                    {cfg.label}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      {active && (
        <div
          style={{
            marginTop: '16px',
            background: '#f8f8f8',
            borderRadius: '8px',
            padding: '16px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span
              style={{
                fontSize: '12px',
                fontWeight: '700',
                color: statusConfig[active.status].color,
                background: statusConfig[active.status].bg,
                padding: '4px 12px',
                borderRadius: '99px',
                border: `1px solid ${statusConfig[active.status].border}`,
              }}
            >
              {statusConfig[active.status].label}
            </span>
            <button
              onClick={() => setActiveId(null)}
              aria-label="Close"
              style={{ border: 'none', background: 'none', fontSize: '18px', cursor: 'pointer', color: '#888', lineHeight: 1 }}
            >
              ×
            </button>
          </div>
          <p style={{ fontSize: '13px', color: '#444', lineHeight: '1.6', margin: '0 0 8px' }}>
            {active.text}
          </p>
          <p style={{ fontSize: '12px', color: '#888', margin: 0 }}>
            Source: {active.source}
          </p>
        </div>
      )}
    </div>
  )
}