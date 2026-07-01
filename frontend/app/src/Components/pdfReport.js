import jsPDF from 'jspdf'

// ─── Design tokens ────────────────────────────────────────────────────────────
const NAVY    = [12,  36,  77]   // #0C244D — primary brand
const NAVY2   = [26,  58, 107]   // slightly lighter navy for accents
const INK     = [22,  24,  27]   // near-black body text
const BODY    = [55,  58,  65]   // paragraph text
const MUTED   = [110, 114, 122]  // captions, labels
const RULE    = [218, 221, 227]  // dividers
const BGCARD  = [248, 249, 251]  // card backgrounds
const WHITE   = [255, 255, 255]

const STATUS = {
  supported:    { hex: '#16a34a', rgb: [22, 163, 74],   label: 'Supported' },
  partial:      { hex: '#ca8a04', rgb: [202, 138, 4],   label: 'Partially Supported' },
  unsupported:  { hex: '#dc2626', rgb: [220, 38, 38],   label: 'Unsupported' },
  hallucinated: { hex: '#7c3aed', rgb: [124, 58, 237],  label: 'Hallucinated' },
  insufficient: { hex: '#6b7280', rgb: [107, 114, 128], label: 'Insufficient Evidence' },
}

// ─── Utility ──────────────────────────────────────────────────────────────────

function rgb(hex) {
  const h = (hex || '#888').replace('#', '')
  const n = parseInt(h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function loadImg(url) {
  return new Promise(res => {
    if (!url) return res(null)
    const img = new window.Image()
    img.onload = () => {
      try {
        const c = document.createElement('canvas')
        c.width = img.width; c.height = img.height
        c.getContext('2d').drawImage(img, 0, 0)
        res(c.toDataURL('image/png'))
      } catch { res(null) }
    }
    img.onerror = () => res(null)
    img.src = url
  })
}

// Set font + size + color together
function f(doc, sz, style, color) {
  doc.setFont('helvetica', style || 'normal')
  doc.setFontSize(sz)
  doc.setTextColor(...(color || INK))
}

// Horizontal line
function hline(doc, x, y, x2, color, lw) {
  doc.setDrawColor(...(color || RULE))
  doc.setLineWidth(lw || 0.25)
  doc.line(x, y, x2, y)
}

// Vertical line
function vline(doc, x, y1, y2, color, lw) {
  doc.setDrawColor(...(color || RULE))
  doc.setLineWidth(lw || 0.25)
  doc.line(x, y1, x, y2)
}

// Filled rect helper
function fill(doc, color, x, y, w, h) {
  doc.setFillColor(...color)
  doc.rect(x, y, w, h, 'F')
}

// ─── Running header ───────────────────────────────────────────────────────────

function header(doc, { W, mg, logo, fileShort }) {
  fill(doc, WHITE, 0, 0, W, 20)
  const logoW = 10
  if (logo) { doc.addImage(logo, 'PNG', mg, 4, logoW, logoW); }
  const tx = logo ? mg + logoW + 4 : mg
  f(doc, 9, 'bold', NAVY); doc.text('verifAi', tx, 11)
  f(doc, 6.5, 'normal', MUTED); doc.text(fileShort, tx + 18, 11)
  hline(doc, 0, 20, W, RULE, 0.4)
}

// ─── Running footer ───────────────────────────────────────────────────────────

function footer(doc, { W, H, mg, cw, pg, total }) {
  hline(doc, 0, H - 14, W, RULE, 0.4)
  f(doc, 6, 'italic', MUTED)
  doc.text('VerifAi uses AI-assisted analysis. Results may contain errors — verify critical claims against original sources.', mg, H - 8, { maxWidth: cw - 24 })
  f(doc, 6.5, 'normal', MUTED)
  doc.text(`${pg} / ${total}`, W - mg, H - 8, { align: 'right' })
}

// ─── Cover page ───────────────────────────────────────────────────────────────

function drawCover(doc, { W, H, mg, cw, logo, file, score, label, scoreColor, items }) {
  const panelW = W * 0.42   // left navy panel width
  const gap    = 10          // gap between panel and right content

  // Full navy left panel
  fill(doc, NAVY, 0, 0, panelW, H)

  // Brand in panel
  if (logo) doc.addImage(logo, 'PNG', mg, 18, 18, 18)
  f(doc, 20, 'bold', WHITE)
  doc.text('verifAi', mg, logo ? 46 : 36)
  f(doc, 7.5, 'normal', [150, 175, 215])
  doc.text('AI Citation Verification', mg, 53)

  // Thin separator line in panel
  doc.setDrawColor(255, 255, 255); doc.setLineWidth(0.3); doc.setLineDashPattern([1, 1.5], 0)
  doc.line(mg, 60, panelW - mg, 60)
  doc.setLineDashPattern([], 0)

  // Score in panel
  const [sr, sg, sb] = rgb(scoreColor)
  f(doc, 7, 'bold', [150, 175, 215])
  doc.text('CREDIBILITY SCORE', mg, 74)

  f(doc, 42, 'bold', [sr, sg, sb])
  doc.text(`${score.toFixed(1)}%`, mg, 102)

  f(doc, 12, 'bold', [sr, sg, sb])
  doc.text(label, mg, 112)

  // Stacked bar in panel
  const bY = 120, bH = 5, bW = panelW - mg * 2
  const total = items.reduce((s, i) => s + i.count, 0)
  fill(doc, [50, 75, 120], mg, bY, bW, bH)
  let bx = mg
  items.forEach(item => {
    const segW = total > 0 ? (item.count / total) * bW : 0
    if (segW > 0) { fill(doc, rgb(item.color), bx, bY, segW, bH); bx += segW }
  })

  // Legend in panel (two columns)
  let legY = bY + 12
  items.forEach((item, i) => {
    const col = i % 2, row = Math.floor(i / 2)
    const lx = mg + col * ((bW + mg) / 2)
    const ly = legY + row * 8
    fill(doc, rgb(item.color), lx, ly - 2.5, 3, 3)
    f(doc, 7, 'normal', [200, 210, 225])
    doc.text(`${item.label}`, lx + 5, ly)
    f(doc, 7, 'bold', WHITE)
    doc.text(`${item.count}`, lx + 5 + (bW / 2 - mg * 0.4), ly, { align: 'right' })
  })

  // ── Right side ────────────────────────────────────────────────────────────
  const rx = panelW + gap  // right panel start x
  const rcw = W - rx - mg  // right content width

  // Report title
  let ry = 28
  f(doc, 7.5, 'bold', MUTED)
  doc.text('VERIFICATION REPORT', rx, ry); ry += 8

  f(doc, 15, 'bold', INK)
  const titleLines = doc.splitTextToSize(file, rcw)
  doc.text(titleLines.slice(0, 3), rx, ry)
  ry += Math.min(titleLines.length, 3) * 7.5 + 4

  hline(doc, rx, ry, W - mg); ry += 8

  // Three stat boxes
  const boxW = (rcw - 6) / 3
  const statData = [
    { v: String(total), l: 'Total Claims' },
    { v: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }), l: 'Date Generated' },
    { v: 'Llama 4', l: 'AI Model' },
  ]
  statData.forEach((s, i) => {
    const bx2 = rx + i * (boxW + 3)
    fill(doc, BGCARD, bx2, ry, boxW, 20)
    f(doc, 13, 'bold', NAVY); doc.text(s.v, bx2 + 5, ry + 11)
    f(doc, 6.5, 'normal', MUTED); doc.text(s.l, bx2 + 5, ry + 18)
  })
  ry += 28

  hline(doc, rx, ry, W - mg); ry += 8

  // Verdict breakdown — simple table
  f(doc, 8, 'bold', NAVY); doc.text('Verdict Breakdown', rx, ry); ry += 8

  items.forEach(item => {
    const pct = total > 0 ? Math.round((item.count / total) * 100) : 0
    const barFill = total > 0 ? ((item.count / total) * rcw) : 0

    f(doc, 7.5, 'normal', BODY); doc.text(item.label, rx, ry)
    f(doc, 7.5, 'bold', INK); doc.text(`${item.count}`, W - mg - 16, ry, { align: 'right' })
    f(doc, 7, 'normal', MUTED); doc.text(`${pct}%`, W - mg, ry, { align: 'right' })

    // Thin bar below label
    fill(doc, RULE, rx, ry + 2, rcw, 1.5)
    if (barFill > 0) fill(doc, rgb(item.color), rx, ry + 2, barFill, 1.5)

    ry += 10
  })

  ry += 4
  hline(doc, rx, ry, W - mg); ry += 8

  // Methodology — compact numbered list
  f(doc, 8, 'bold', NAVY); doc.text('Methodology', rx, ry); ry += 7

  const steps = [
    'PDF text extracted and parsed.',
    'Citations identified; DOIs resolved via CrossRef and OpenAlex.',
    'Claims linked to citations via Llama 4.',
    'Sources retrieved and compared via RAG pipeline.',
    'Each claim receives a verdict and confidence score.',
  ]
  steps.forEach((step, i) => {
    f(doc, 7, 'bold', [sr, sg, sb]); doc.text(`${i + 1}.`, rx, ry)
    f(doc, 7, 'normal', BODY); doc.text(step, rx + 6, ry)
    ry += 7
  })

  ry += 4
  hline(doc, rx, ry, W - mg); ry += 7

  // Disclaimer
  f(doc, 6.5, 'italic', MUTED)
  const disc = doc.splitTextToSize(
    'Disclaimer: VerifAi uses AI-assisted analysis. Results may contain errors — verify critical claims against original sources before drawing conclusions.',
    rcw
  )
  doc.text(disc, rx, ry)
}

// ─── Category reference page ──────────────────────────────────────────────────

function drawCategories(doc, { W, H, mg, cw, logo, fileShort }) {
  doc.addPage()
  header(doc, { W, mg, logo, fileShort })
  let y = 28

  f(doc, 11, 'bold', NAVY); doc.text('Verdict Category Reference', mg, y)
  hline(doc, mg, y + 4, W - mg, NAVY, 0.5)
  y += 14

  const cats = [
    { key: 'Supported', color: '#16a34a',
      desc: 'A valid DOI was resolved, the source text was retrieved, similarity ≥ 0.50, and the language model confirmed the claim matches the source.',
      note: 'Strongest indicator of citation accuracy.' },
    { key: 'Partially Supported', color: '#ca8a04',
      desc: 'The source is relevant but does not fully confirm all aspects of the claim. Common causes: paraphrasing that overstates results, missing caveats, or combined findings from separate studies.',
      note: 'Review the AI reasoning below each claim for the specific discrepancy.' },
    { key: 'Unsupported', color: '#dc2626',
      desc: 'The source was retrieved and read, but the claim is absent from or contradicts the source content. Distinct from Insufficient Evidence — the evidence was found but does not support the claim.',
      note: 'Consider revising or removing this claim from the paper.' },
    { key: 'Hallucinated', color: '#7c3aed',
      desc: 'The cited DOI is invalid or cannot be resolved to any existing publication. This verdict is assigned by a deterministic rule, not the AI model.',
      note: 'Strongest signal of a fabricated citation — the source may not exist.' },
    { key: 'Insufficient Evidence', color: '#6b7280',
      desc: 'Not enough text could be retrieved from the cited source. Causes include: paywall, abstract-only access, similarity below threshold, or a malformed model response.',
      note: 'Upload the source PDF manually on the results page to enable re-verification.' },
  ]

  cats.forEach(cat => {
    const [cr, cg, cb] = rgb(cat.color)
    const dLines = doc.splitTextToSize(cat.desc, cw - 14)
    const nLines = doc.splitTextToSize(cat.note, cw - 14)
    const bh = 10 + dLines.length * 5 + 4 + nLines.length * 5 + 6

    if (y + bh > H - 20) {
      doc.addPage(); header(doc, { W, mg, logo, fileShort }); y = 28
    }

    // Card
    fill(doc, BGCARD, mg, y, cw, bh)
    fill(doc, [cr, cg, cb], mg, y, 3, bh)

    f(doc, 9, 'bold', [cr, cg, cb]); doc.text(cat.key, mg + 9, y + 8)
    f(doc, 8, 'normal', BODY); doc.text(dLines, mg + 9, y + 15)

    const noteY = y + 15 + dLines.length * 5 + 3
    f(doc, 7.5, 'italic', MUTED); doc.text(`→ ${cat.note}`, mg + 9, noteY)

    y += bh + 6
  })
}

// ─── Claim card ───────────────────────────────────────────────────────────────

function drawClaim(doc, { claim, statusLabel, mg, cw, W, y }) {
  const s = STATUS[claim.status] || { rgb: [107, 114, 128], label: statusLabel || claim.status }
  const [cr, cg, cb] = s.rgb

  const conf       = Math.round((claim.confidence || 0) * 100)
  const textW      = cw - 14
  const qLines     = doc.splitTextToSize(`"${claim.text}"`, textW)
  const rLines     = doc.splitTextToSize(claim.reasoning || '', textW)
  const wLines     = claim.warning ? doc.splitTextToSize(claim.warning, textW) : []

  // Height calculation
  let h = 8                            // top padding + claim id row
  h += qLines.length * 5.2 + 4        // quote
  if (claim.authorLine) h += 5.5
  if (claim.doi)        h += 5
  h += rLines.length * 4.5 + 3        // reasoning
  if (wLines.length)   h += wLines.length * 4.5 + 3
  h += 10                              // confidence row + bottom padding

  // Card background
  fill(doc, BGCARD, mg, y, cw, h)
  fill(doc, [cr, cg, cb], mg, y, 3, h)

  // Claim number — top left
  f(doc, 6.5, 'bold', MUTED)
  doc.text(`#${claim.displayId}`, mg + 9, y + 6.5)

  // Status badge — top right (colored text, no pill)
  f(doc, 7, 'bold', [cr, cg, cb])
  doc.text(s.label, W - mg - 2, y + 6.5, { align: 'right' })

  let iy = y + 12

  // Claim text
  f(doc, 8.5, 'italic', INK)
  doc.text(qLines, mg + 9, iy); iy += qLines.length * 5.2 + 4

  // Source line
  if (claim.authorLine) {
    f(doc, 7, 'normal', MUTED)
    const src = claim.authorLine.length > 90 ? claim.authorLine.slice(0, 87) + '…' : claim.authorLine
    doc.text(`Source: ${src}`, mg + 9, iy); iy += 5.5
  }
  if (claim.doi) {
    f(doc, 7, 'normal', [50, 110, 220])
    doc.text(`DOI: ${claim.doi}`, mg + 9, iy); iy += 5
  }

  // Reasoning
  f(doc, 7.5, 'normal', MUTED)
  doc.text(rLines, mg + 9, iy); iy += rLines.length * 4.5 + 3

  // Warning
  if (wLines.length) {
    f(doc, 7, 'italic', [160, 80, 10])
    doc.text(wLines, mg + 9, iy); iy += wLines.length * 4.5 + 3
  }

  // Confidence row
  const barX = mg + 9, barW = 40
  f(doc, 6.5, 'normal', MUTED); doc.text('Confidence', barX, iy + 3)
  fill(doc, RULE, barX + 26, iy + 0.5, barW, 2.5)
  const confColor = conf > 70 ? [22, 163, 74] : conf > 40 ? [202, 138, 4] : [220, 38, 38]
  fill(doc, confColor, barX + 26, iy + 0.5, Math.max(barW * conf / 100, 1.5), 2.5)
  f(doc, 6.5, 'bold', MUTED); doc.text(`${conf}%`, barX + 26 + barW + 4, iy + 3)

  return y + h + 5  // 5mm gap between claims
}

// ─── Main export ──────────────────────────────────────────────────────────────

export async function generateVerificationPdf({
  claims, statusConfig, summaryItems, fileName, logo,
  credibilityScore = 0, credibilityLabel = 'Unknown', credibilityColor = '#888888',
}) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  const W   = doc.internal.pageSize.getWidth()
  const H   = doc.internal.pageSize.getHeight()
  const mg  = 14
  const cw  = W - mg * 2

  const logoB64   = logo ? await loadImg(logo) : null
  const fileShort = fileName.length > 60 ? fileName.slice(0, 57) + '…' : fileName
  const ctx       = { W, H, mg, cw, logo: logoB64, fileShort }

  // ── Cover (page 1, no header/footer)
  drawCover(doc, { ...ctx, file: fileShort, score: credibilityScore, label: credibilityLabel, scoreColor: credibilityColor, items: summaryItems })

  // ── Category reference (page 2+)
  drawCategories(doc, ctx)

  // ── Claims pages
  doc.addPage()
  header(doc, ctx)
  let y = 28

  const newPage = () => { doc.addPage(); header(doc, ctx); y = 28 }
  const guard   = (need) => { if (y + need > H - 18) newPage() }

  // Group by source (authorLine)
  const groups = {}
  claims.forEach(c => {
    const key = c.authorLine || 'Unknown Source'
    if (!groups[key]) groups[key] = []
    groups[key].push(c)
  })

  let first = true
  Object.entries(groups).forEach(([paper, grpClaims]) => {
    guard(20)
    if (!first) y += 6
    first = false

    // Source heading
    f(doc, 8, 'bold', NAVY)
    const paperLines = doc.splitTextToSize(paper, cw)
    doc.text(paperLines[0], mg, y)
    hline(doc, mg, y + 4, W - mg, NAVY, 0.5)
    y += 12

    grpClaims.forEach(claim => {
      const statusLabel = statusConfig[claim.status]?.label || claim.status
      // Height estimation (mirrors drawClaim)
      const textW  = cw - 14
      const qL     = doc.splitTextToSize(`"${claim.text}"`, textW)
      const rL     = doc.splitTextToSize(claim.reasoning || '', textW)
      const wL     = claim.warning ? doc.splitTextToSize(claim.warning, textW) : []
      let bh       = 8 + qL.length * 5.2 + 4 + rL.length * 4.5 + 3 + 10
      if (claim.authorLine) bh += 5.5
      if (claim.doi)        bh += 5
      if (wL.length)        bh += wL.length * 4.5 + 3
      guard(bh + 5)

      y = drawClaim(doc, { claim, statusLabel, mg, cw, W, y })
    })
  })

  // ── Footers on all pages except cover
  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 2; i <= totalPages; i++) {
    doc.setPage(i)
    footer(doc, { W, H, mg, cw, pg: i - 1, total: totalPages - 1 })
  }

  doc.save(`verifai_report_${fileName.replace(/\.pdf$/i, '')}.pdf`)
}
