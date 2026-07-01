import jsPDF from 'jspdf'

// ─── Tokens ───────────────────────────────────────────────────────────────────
const NAVY  = [12,  36,  77]
const INK   = [20,  22,  26]
const BODY  = [52,  55,  62]
const MUTED = [108, 112, 120]
const RULE  = [212, 215, 222]
const CARD  = [248, 249, 251]
const WHITE = [255, 255, 255]

const STATUS_MAP = {
  supported:    { rgb: [22,  163,  74], label: 'Supported' },
  partial:      { rgb: [180, 110,   4], label: 'Partially Supported' },
  unsupported:  { rgb: [200,  35,  35], label: 'Unsupported' },
  hallucinated: { rgb: [110,  45, 210], label: 'Hallucinated' },
  insufficient: { rgb: [100, 105, 115], label: 'Insufficient Evidence' },
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function hexRgb(hex) {
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

// Set font, size and colour in one call (Times New Roman throughout)
function tf(doc, size, style, color) {
  doc.setFont('times', style || 'normal')
  doc.setFontSize(size)
  doc.setTextColor(...(color || INK))
}

// Draw a horizontal rule
function hr(doc, x, y, x2, color, w) {
  doc.setDrawColor(...(color || RULE))
  doc.setLineWidth(w || 0.3)
  doc.line(x, y, x2, y)
}

// Fill a rectangle
function rect(doc, color, x, y, w, h) {
  doc.setFillColor(...color)
  doc.rect(x, y, w, h, 'F')
}

// Wrap text and return line array — single source of truth
function wrap(doc, text, width) {
  return doc.splitTextToSize(text || '', width)
}

// Line height constants (keep in sync everywhere)
const LH_BODY    = 5.6  // body text
const LH_SMALL   = 5.0  // small / meta text
const LH_REASON  = 5.2  // reasoning text

// ─── Header (all content pages) ───────────────────────────────────────────────

function drawHeader(doc, { W, mg, logo }) {
  rect(doc, WHITE, 0, 0, W, 26)
  if (logo) doc.addImage(logo, 'PNG', mg, 3, 20, 20)   // 20×20 mm logo
  const tx = logo ? mg + 24 : mg
  tf(doc, 14, 'bold', NAVY);  doc.text('verifAi', tx, 15)
  tf(doc, 7.5, 'normal', MUTED)
  doc.text('AI-Powered Citation Verification Report', tx, 22)
  hr(doc, 0, 26, W, RULE, 0.5)
}

// ─── Footer ───────────────────────────────────────────────────────────────────

function drawFooter(doc, { W, H, mg, cw, pg, total }) {
  hr(doc, 0, H - 16, W, RULE, 0.4)
  tf(doc, 6.5, 'italic', MUTED)
  doc.text(
    'VerifAi uses AI-assisted analysis. Results may contain errors — verify critical claims against original sources.',
    mg, H - 9, { maxWidth: cw - 28 }
  )
  tf(doc, 7.5, 'bold', MUTED)
  doc.text(`Page ${pg} / ${total}`, W - mg, H - 9, { align: 'right' })
}

// ─── Claims summary section ───────────────────────────────────────────────────

function drawSummary(doc, { mg, cw, W, items, y }) {
  const total = items.reduce((s, i) => s + i.count, 0)

  // Section title
  tf(doc, 11, 'bold', INK); doc.text('Claims Summary', mg, y); y += 5
  hr(doc, mg, y, mg + cw, RULE); y += 8

  // Legend grid — 2 columns
  const colW = cw / 2
  items.forEach((item, i) => {
    const col = i % 2, row = Math.floor(i / 2)
    const ix = mg + col * colW
    const iy = y + row * 9

    doc.setFillColor(...hexRgb(item.color))
    doc.circle(ix + 3, iy - 1.5, 2.5, 'F')
    tf(doc, 9, 'normal', BODY);  doc.text(item.label, ix + 8, iy)
    tf(doc, 9, 'bold',   INK);   doc.text(String(item.count), ix + colW - 8, iy, { align: 'right' })
  })

  const rows = Math.ceil(items.length / 2)
  y += rows * 9 + 5

  // Stacked bar
  const barH = 5, barW = cw
  rect(doc, [220, 222, 228], mg, y, barW, barH)
  let bx = mg
  items.forEach(item => {
    const sw = total > 0 ? (item.count / total) * barW : 0
    if (sw > 0.1) { rect(doc, hexRgb(item.color), bx, y, sw, barH); bx += sw }
  })

  y += barH + 12
  return y
}

// ─── Single claim card ────────────────────────────────────────────────────────

// Returns the EXACT height this card will occupy — used both for page-break guard
// and for drawing the card background. Must stay in sync.
function claimHeight(doc, claim, textW) {
  const qLines = wrap(doc, `"${claim.text}"`, textW)
  const rLines = wrap(doc, claim.reasoning || '', textW)
  const wLines = claim.warning ? wrap(doc, claim.warning, textW) : []

  let h = 8                          // top padding (id row)
  h += qLines.length * LH_BODY + 6  // quote block
  if (claim.authorLine) h += LH_SMALL + 2
  if (claim.doi)        h += LH_SMALL + 1
  h += 4                             // gap before reasoning
  h += rLines.length * LH_REASON + 4
  if (wLines.length) h += wLines.length * LH_SMALL + 4
  h += 9                             // confidence row + bottom padding

  return h
}

function drawClaim(doc, { claim, idx, statusLabel, mg, cw, W, y }) {
  const s = STATUS_MAP[claim.status] || { rgb: [100, 105, 115], label: statusLabel || claim.status }
  const [cr, cg, cb] = s.rgb
  const textW = cw - 18
  const conf  = Math.round((claim.confidence || 0) * 100)

  const h = claimHeight(doc, claim, textW)

  // Card background + left accent bar
  rect(doc, CARD, mg, y, cw, h)
  rect(doc, [cr, cg, cb], mg, y, 4, h)

  // ── Id row
  tf(doc, 7.5, 'normal', MUTED)
  doc.text(`Claim ${idx}`, mg + 12, y + 7)

  // Status pill (outlined, right side)
  const pillLabel = s.label
  tf(doc, 7.5, 'bold', [cr, cg, cb])
  const pillW = doc.getTextWidth(pillLabel) + 10
  doc.setDrawColor(cr, cg, cb); doc.setLineWidth(0.4)
  doc.roundedRect(W - mg - pillW - 1, y + 2, pillW, 7, 1.5, 1.5, 'D')
  doc.text(pillLabel, W - mg - pillW / 2 - 1, y + 7.2, { align: 'center' })

  let iy = y + 13

  // ── Claim quote
  const qLines = wrap(doc, `"${claim.text}"`, textW)
  tf(doc, 10, 'italic', INK)
  doc.text(qLines, mg + 12, iy)
  iy += qLines.length * LH_BODY + 6

  // ── Source / DOI
  if (claim.authorLine) {
    tf(doc, 8, 'normal', MUTED)
    doc.text(`Source: ${claim.authorLine}`, mg + 12, iy, { maxWidth: textW })
    iy += LH_SMALL + 2
  }
  if (claim.doi) {
    tf(doc, 8, 'normal', [45, 100, 215])
    doc.text(`DOI: ${claim.doi}`, mg + 12, iy, { maxWidth: textW })
    iy += LH_SMALL + 1
  }

  iy += 4  // gap before reasoning

  // ── AI reasoning
  const rLines = wrap(doc, claim.reasoning || '', textW)
  tf(doc, 8.5, 'italic', BODY)
  doc.text(rLines, mg + 12, iy)
  iy += rLines.length * LH_REASON + 4

  // ── Warning
  if (claim.warning) {
    const wLines = wrap(doc, claim.warning, textW)
    tf(doc, 8, 'italic', [165, 80, 10])
    doc.text(wLines, mg + 12, iy)
    iy += wLines.length * LH_SMALL + 4
  }

  // ── Confidence bar
  const barX = mg + 12, barW = 50
  tf(doc, 8, 'normal', MUTED); doc.text('Confidence', barX, iy + 3.5)
  rect(doc, RULE, barX + 28, iy + 1, barW, 3)
  const cRgb = conf > 70 ? [22, 163, 74] : conf > 40 ? [180, 110, 4] : [200, 35, 35]
  rect(doc, cRgb, barX + 28, iy + 1, Math.max(barW * conf / 100, 1.5), 3)
  tf(doc, 8, 'bold', MUTED); doc.text(`${conf}%`, barX + 28 + barW + 6, iy + 3.5)

  return y + h + 6   // 6 mm gap between cards
}

// ─── Main export ──────────────────────────────────────────────────────────────

export async function generateVerificationPdf({
  claims, statusConfig, summaryItems, fileName, logo,
  credibilityScore = 0, credibilityLabel = 'Unknown', credibilityColor = '#888888',
}) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  const W  = doc.internal.pageSize.getWidth()
  const H  = doc.internal.pageSize.getHeight()
  const mg = 16
  const cw = W - mg * 2

  const logoB64   = logo ? await loadImg(logo) : null
  const headerCtx = { W, mg, logo: logoB64 }
  const footerCtx = { W, H, mg, cw }

  // ── Page 1: summary + first claims ──────────────────────────────────────────

  drawHeader(doc, headerCtx)

  // Position content below header
  let y = 34

  // Credibility score card
  const scoreDesc = credibilityScore >= 80
    ? 'The majority of claims are well-supported by their cited sources.'
    : credibilityScore >= 50
    ? 'Some claims are inaccurate or unsupported by their cited sources.'
    : 'A significant portion of claims could not be verified or are unsupported.'

  const [cr, cg, cb] = hexRgb(credibilityColor)
  rect(doc, CARD, mg, y, cw, 30)
  rect(doc, [cr, cg, cb], mg, y, 4, 30)
  tf(doc, 20, 'bold', [cr, cg, cb])
  doc.text(`${credibilityScore.toFixed(1)}%`, mg + 12, y + 13)
  const scoreNumW = doc.getTextWidth(`${credibilityScore.toFixed(1)}%`)
  tf(doc, 13, 'bold', [cr, cg, cb])
  doc.text(`— ${credibilityLabel}`, mg + 12 + scoreNumW + 2, y + 13)
  tf(doc, 9, 'italic', BODY)
  doc.text(scoreDesc, mg + 12, y + 23)
  y += 40

  // Summary card
  y = drawSummary(doc, { mg, cw, W, items: summaryItems, y })

  // Claims overview heading
  tf(doc, 11, 'bold', INK); doc.text('Claims Overview', mg, y); y += 5
  hr(doc, mg, y, mg + cw, RULE); y += 10

  // ── Render claims ────────────────────────────────────────────────────────────

  const newPage = () => {
    doc.addPage()
    drawHeader(doc, headerCtx)
    y = 34
  }

  const guard = (need) => {
    if (y + need > H - 20) newPage()
  }

  claims.forEach((claim, i) => {
    const textW = cw - 18
    const h = claimHeight(doc, claim, textW)
    guard(h + 6)
    y = drawClaim(doc, {
      claim,
      idx: i + 1,
      statusLabel: statusConfig[claim.status]?.label || claim.status,
      mg, cw, W, y,
    })
  })

  // ── Footers on every page ────────────────────────────────────────────────────

  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i)
    drawFooter(doc, { ...footerCtx, pg: i, total: totalPages })
  }

  doc.save(`verifai_report_${fileName.replace(/\.pdf$/i, '')}.pdf`)
}
