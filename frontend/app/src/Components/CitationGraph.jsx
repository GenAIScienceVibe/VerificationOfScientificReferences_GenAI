import { useState, useMemo } from 'react'

const HUB_R = 20
const SOURCE_R = 9
const CLAIM_R = 7
const RING_1 = 130
const RING_2 = 300

const DEMO_EXTRA_CLAIMS = [
  {
    id: 'demo-1',
    status: 'partial',
    text: '"The same exercise program was also linked to a 15% drop in resting heart rate [Johnson et al., 2019]"',
    source: 'Johnson et al., 2019',
    isDemo: true,
  },
  {
    id: 'demo-2',
    status: 'supported',
    text: '"The trial population included 1,200 adults across three age groups [Smith et al., 2021]"',
    source: 'Smith et al., 2021',
    isDemo: true,
  },
  {
    id: 'demo-3',
    status: 'unsupported',
    text: '"The same dataset also shows Y causing Z in adolescents [White et al., 2022]"',
    source: 'White et al., 2022',
    isDemo: true,
  },
  {
    id: 'demo-4',
    status: 'supported',
    text: '"Vitamin D supplementation is associated with reduced fracture risk in adults over 60 [Anderson et al., 2018]"',
    source: 'Anderson et al., 2018',
    isDemo: true,
  },
  {
    id: 'demo-5',
    status: 'supported',
    text: '"Cognitive behavioral therapy shows lasting effectiveness for chronic insomnia [Martinez et al., 2020]"',
    source: 'Martinez et al., 2020',
    isDemo: true,
  },
  {
    id: 'demo-6',
    status: 'partial',
    text: '"Intermittent fasting was linked to improved metabolic markers in 60% of participants [Lee et al., 2022]"',
    source: 'Lee et al., 2022',
    isDemo: true,
  },
  {
    id: 'demo-7',
    status: 'unsupported',
    text: '"Meditation reduces anxiety symptoms by 50% [Kumar et al., 2021]"',
    source: 'Kumar et al., 2021',
    isDemo: true,
  },
]

function buildRadialLayout(allClaims) {
  const bySource = new Map()
  allClaims.forEach((claim) => {
    const key = claim.source || 'Unknown source'
    if (!bySource.has(key)) bySource.set(key, [])
    bySource.get(key).push(claim)
  })

  const sourceEntries = Array.from(bySource.entries())
  const total = sourceEntries.length || 1
  const cx = 440
  const cy = 380

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

function labelAnchor(x, y, angle, dist = 12) {
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  if (Math.abs(cos) > 0.35) {
    const side = cos > 0 ? 1 : -1
    return { x: x + side * dist, y: y + (sin >= 0 ? 4 : -4), anchor: side > 0 ? 'start' : 'end' }
  }
  const vSide = sin >= 0 ? 1 : -1
  return { x: x + dist, y: y + vSide * dist, anchor: 'start' }
}

export default function CitationGraph({ claims, statusConfig, documentLabel = 'This paper', statusFilter = 'all' }) {
  const [activeId, setActiveId] = useState(null)

  const allClaims = useMemo(() => [...claims, ...DEMO_EXTRA_CLAIMS], [claims])
  const { cx, cy, sourceNodes, claimNodes } = useMemo(() => buildRadialLayout(allClaims), [allClaims])
  const active = allClaims.find((c) => c.id === activeId)
  const highlighted = statusFilter !== 'all' ? statusFilter : null

  if (allClaims.length === 0) return null

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
        <svg width="100%" viewBox="0 0 900 760" style={{ display: 'block', minWidth: '700px' }}>
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
          <text x={cx} y={cy - HUB_R - 8} textAnchor="middle" fontSize="10" fontWeight="600" fill="#1a3a6b">
            {documentLabel}
          </text>

          {sourceNodes.map((s) => {
            const lbl = labelAnchor(s.x, s.y, s.angle, 13)
            const sourceHasMatch = highlighted && claimNodes.some((c) => c.sourceId === s.id && c.status === highlighted)
            const dimmed = highlighted && !sourceHasMatch
            return (
              <g key={s.id} opacity={dimmed ? 0.35 : 1}>
                <circle cx={s.x} cy={s.y} r={SOURCE_R} fill="white" stroke="#1a3a6b" strokeWidth="1.5" />
                <text x={lbl.x} y={lbl.y - 4} textAnchor={lbl.anchor} fontSize="10" fontWeight="600" fill="#111">
                  {s.label}
                </text>
                <text x={lbl.x} y={lbl.y + 9} textAnchor={lbl.anchor} fontSize="9" fill="#888">
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
            const lbl = labelAnchor(c.x, c.y, c.angle, 11)
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
                {(matched) && (
                  <text x={lbl.x} y={lbl.y} textAnchor={lbl.anchor} fontSize="9.5" fill={cfg.color} fontWeight="600">
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
            {active.isDemo ? ' (example citation, for illustration)' : ''}
          </p>
        </div>
      )}
    </div>
  )
}