import jsPDF from 'jspdf'

// ─── Palette ──────────────────────────────────────────────────────────────────
const NAVY   = [12,  36,  77]
const INK    = [20,  22,  25]
const BODY   = [50,  53,  60]
const MUTED  = [100, 104, 112]
const RULE   = [210, 214, 220]
const CARD   = [247, 248, 250]
const WHITE  = [255, 255, 255]

const STATUS = {
  supported:    { rgb: [22,  163, 74],  label: 'Supported' },
  partial:      { rgb: [180, 110,  4],  label: 'Partially Supported' },
  unsupported:  { rgb: [200,  35, 35],  label: 'Unsupported' },
  hallucinated: { rgb: [110,  45, 210], label: 'Hallucinated' },
  insufficient: { rgb: [100, 105, 115], label: 'Insufficient Evidence' },
}

// ─── Utilities ────────────────────────────────────────────────────────────────

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

// Font helper — Times New Roman throughout
function f(doc, sz, style, color) {
  doc.setFont('times', style || 'normal')
  doc.setFontSize(sz)
  doc.setTextColor(...(color || INK))
}

function hline(doc, x, y, x2, color, lw) {
  doc.setDrawColor(...(color || RULE))
  doc.setLineWidth(lw || 0.3)
  doc.line(x, y, x2, y)
}

function box(doc, color, x, y, w, h) {
  doc.setFillColor(...color)
  doc.rect(x, y, w, h, 'F')
}

// ─── Running header ───────────────────────────────────────────────────────────

function header(doc, { W, mg, logo, fileShort }) {
  box(doc, WHITE, 0, 0, W, 22)
  if (logo) doc.addImage(logo, 'PNG', mg, 3, 16, 16)
  const tx = logo ? mg + 20 : mg
  f(doc, 11, 'bold', NAVY); doc.text('verifAi', tx, 13)
  f(doc, 7.5, 'normal', MUTED); doc.text('  —  ' + fileShort, tx + 16, 13)
  hline(doc, 0, 22, W, RULE, 0.5)
}

// ─── Running footer ───────────────────────────────────────────────────────────

function footer(doc, { W, H, mg, cw, pg, total }) {
  hline(doc, 0, H - 16, W, RULE, 0.4)
  f(doc, 7, 'italic', MUTED)
  doc.text(
    'VerifAi uses AI-assisted analysis. Results may contain errors — verify critical claims against original sources.',
    mg, H - 9, { maxWidth: cw - 24 }
  )
  f(doc, 8, 'normal', MUTED)
  doc.text(`${pg} / ${total}`, W - mg, H - 9, { align: 'right' })
}

// ─── Cover ────────────────────────────────────────────────────────────────────

function drawCover(doc, { W, H, mg, cw, logo, file, score, label, scoreColor, items }) {
  const cx = W / 2  // horizontal centre

  // ── Top navy band
  box(doc, NAVY, 0, 0, W, 70)

  // Logo — centred in band, large
  if (logo) {
    const lSize = 36
    doc.addImage(logo, 'PNG', cx - lSize / 2, 10, lSize, lSize)
  }

  // Brand name below logo
  f(doc, 22, 'bold', WHITE)
  doc.text('verifAi', cx, logo ? 56 : 36, { align: 'center' })

  f(doc, 9, 'italic', [160, 185, 220])
  doc.text('AI-Powered Citation Verification', cx, 64, { align: 'center' })

  // ── File title
  let y = 82
  f(doc, 9, 'normal', MUTED); doc.text('Document', cx, y, { align: 'center' }); y += 6
  f(doc, 13, 'bold', INK)
  const titleLines = doc.splitTextToSize(file, cw - 20)
  doc.text(titleLines.slice(0, 2), cx, y, { align: 'center' })
  y += Math.min(titleLines.length, 2) * 7 + 6

  hline(doc, mg + 20, y, W - mg - 20, RULE); y += 10

  // ── Credibility score — large, centred
  const [sr, sg, sb] = rgb(scoreColor)
  f(doc, 9, 'italic', MUTED); doc.text('Credibility Score', cx, y, { align: 'center' }); y += 8
  f(doc, 48, 'bold', [sr, sg, sb]); doc.text(`${score.toFixed(1)}%`, cx, y + 22, { align: 'center' })
  f(doc, 13, 'bold', [sr, sg, sb]); doc.text(label, cx, y + 32, { align: 'center' })
  y += 42

  hline(doc, mg + 20, y, W - mg - 20, RULE); y += 10

  // ── Verdict breakdown table — two columns
  const total = items.reduce((s, i) => s + i.count, 0)
  f(doc, 10, 'bold', INK); doc.text('Verdict Breakdown', cx, y, { align: 'center' }); y += 8

  const colW = (cw - 20) / 2
  items.forEach((item, i) => {
    const col = i % 2, row = Math.floor(i / 2)
    const ix = mg + 10 + col * (colW + 4)
    const iy = y + row * 9

    const [r2, g2, b2] = rgb(item.color)
    box(doc, [r2, g2, b2], ix, iy - 3, 3, 5)
    f(doc, 8.5, 'normal', BODY); doc.text(item.label, ix + 6, iy)
    f(doc, 8.5, 'bold', INK); doc.text(String(item.count), ix + colW - 4, iy, { align: 'right' })
  })

  y += Math.ceil(items.length / 2) * 9 + 6
  hline(doc, mg + 20, y, W - mg - 20, RULE); y += 10

  // ── Meta row
  const metaItems = [
    { l: 'Total Claims', v: String(total) },
    { l: 'Generated', v: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) },
    { l: 'Model', v: 'Llama 4' },
  ]
  const mw = cw / metaItems.length
  metaItems.forEach((m, i) => {
    const mx = mg + i * mw + mw / 2
    f(doc, 13, 'bold', NAVY); doc.text(m.v, mx, y + 8, { align: 'center' })
    f(doc, 7.5, 'normal', MUTED); doc.text(m.l, mx, y + 16, { align: 'center' })
  })

  y += 26
  hline(doc, mg + 20, y, W - mg - 20, RULE); y += 10

  // ── Disclaimer
  f(doc, 7.5, 'italic', MUTED)
  const disc = doc.splitTextToSize(
    'Disclaimer: VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors and accuracy is not guaranteed. Verify critical claims against the original sources before drawing conclusions.',
    cw - 20
  )
  doc.text(disc, cx, y, { align: 'center' })
}

// ─── Category reference page ──────────────────────────────────────────────────

function drawCategories(doc, { W, H, mg, cw, logo, fileShort }) {
  doc.addPage()
  header(doc, { W, mg, logo, fileShort })
  let y = 32

  f(doc, 14, 'bold', NAVY); doc.text('Verdict Category Reference', mg, y)
  hline(doc, mg, y + 4, W - mg, NAVY, 0.6)
  y += 15

  const cats = [
    { key: 'Supported', color: '#16a34a',
      desc: 'A valid DOI was resolved, source text was retrieved, semantic similarity ≥ 0.50, and the language model confirmed the claim matches the source.',
      note: 'Strongest indicator of citation accuracy.' },
    { key: 'Partially Supported', color: '#ca8a04',
      desc: 'The source is relevant but does not fully confirm all aspects. Common causes: paraphrasing that overstates results, missing caveats, or findings from separate studies combined into one claim.',
      note: 'Review the AI reasoning section below each claim for the specific discrepancy.' },
    { key: 'Unsupported', color: '#dc2626',
      desc: 'The source was retrieved and read, but the claim is absent from or contradicts the source content. The distinction from Insufficient Evidence is that evidence was found but does not support the claim.',
      note: 'Consider revising or removing this claim from the paper.' },
    { key: 'Hallucinated', color: '#7c3aed',
      desc: 'The cited DOI is invalid or does not resolve to any existing publication. This verdict is assigned by a deterministic rule — not by the AI model. The source may be entirely fabricated.',
      note: 'Strongest signal of a fabricated citation.' },
    { key: 'Insufficient Evidence', color: '#6b7280',
      desc: 'Not enough text could be retrieved from the cited source. Causes include paywall restrictions, abstract-only access, similarity score below threshold, or a malformed model response.',
      note: 'Upload the source PDF manually on the results page to enable full re-verification.' },
  ]

  cats.forEach(cat => {
    const [cr, cg, cb] = rgb(cat.color)
    const dLines = doc.splitTextToSize(cat.desc, cw - 16)
    const bh = 10 + dLines.length * 5.5 + 6 + 6

    if (y + bh > H - 20) { doc.addPage(); header(doc, { W, mg, logo, fileShort }); y = 32 }

    box(doc, CARD, mg, y, cw, bh)
    box(doc, [cr, cg, cb], mg, y, 4, bh)

    f(doc, 10, 'bold', [cr, cg, cb]); doc.text(cat.key, mg + 11, y + 9)
    f(doc, 8.5, 'normal', BODY); doc.text(dLines, mg + 11, y + 16)
    const noteY = y + 16 + dLines.length * 5.5 + 1
    f(doc, 8, 'italic', MUTED); doc.text(`Note: ${cat.note}`, mg + 11, noteY)

    y += bh + 6
  })
}

// ─── Single claim card ────────────────────────────────────────────────────────

function drawClaim(doc, { claim, statusLabel, mg, cw, W, y }) {
  const s   = STATUS[claim.status] || { rgb: [100, 105, 115], label: statusLabel || claim.status }
  const [cr, cg, cb] = s.rgb
  const conf = Math.round((claim.confidence || 0) * 100)

  const textW  = cw - 16
  const qLines = doc.splitTextToSize(`“${claim.text}”`, textW)
  const rLines = doc.splitTextToSize(claim.reasoning || '', textW)
  const wLines = claim.warning ? doc.splitTextToSize(claim.warning, textW) : []

  let h = 10 + qLines.length * 5.5 + 5
  if (claim.authorLine) h += 6
  if (claim.doi)        h += 5.5
  h += rLines.length * 5 + 5
  if (wLines.length)   h += wLines.length * 5 + 4
  h += 10

  // Card
  box(doc, CARD, mg, y, cw, h)
  box(doc, [cr, cg, cb], mg, y, 4, h)

  // Header row
  f(doc, 8, 'normal', MUTED);       doc.text(`Claim ${claim.displayId}`, mg + 11, y + 8)
  f(doc, 8.5, 'bold', [cr, cg, cb]); doc.text(s.label, W - mg - 2, y + 8, { align: 'right' })

  let iy = y + 15

  // Claim text
  f(doc, 10, 'italic', INK)
  doc.text(qLines, mg + 11, iy); iy += qLines.length * 5.5 + 5

  // Source + DOI
  if (claim.authorLine) {
    f(doc, 8, 'normal', MUTED)
    const src = claim.authorLine.length > 95 ? claim.authorLine.slice(0, 92) + '…' : claim.authorLine
    doc.text(`Source: ${src}`, mg + 11, iy); iy += 6
  }
  if (claim.doi) {
    f(doc, 8, 'normal', [45, 100, 210])
    doc.text(`DOI: ${claim.doi}`, mg + 11, iy); iy += 5.5
  }

  // Reasoning
  f(doc, 8.5, 'normal', BODY)
  doc.text(rLines, mg + 11, iy); iy += rLines.length * 5 + 4

  // Warning
  if (wLines.length) {
    f(doc, 8, 'italic', [155, 75, 10])
    doc.text(wLines, mg + 11, iy); iy += wLines.length * 5 + 3
  }

  // Confidence bar
  const barX = mg + 11, barW = 45
  f(doc, 8, 'normal', MUTED); doc.text('Confidence', barX, iy + 3.5)
  box(doc, RULE, barX + 28, iy + 0.5, barW, 3)
  const confRgb = conf > 70 ? [22, 163, 74] : conf > 40 ? [180, 110, 4] : [200, 35, 35]
  box(doc, confRgb, barX + 28, iy + 0.5, Math.max(barW * conf / 100, 1.5), 3)
  f(doc, 8, 'bold', MUTED); doc.text(`${conf}%`, barX + 28 + barW + 5, iy + 3.5)

  return y + h + 5
}

// ─── Main export ──────────────────────────────────────────────────────────────

export async function generateVerificationPdf({
  claims, statusConfig, summaryItems, fileName, logo,
  credibilityScore = 0, credibilityLabel = 'Unknown', credibilityColor = '#888888',
}) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  const W   = doc.internal.pageSize.getWidth()
  const H   = doc.internal.pageSize.getHeight()
  const mg  = 16
  const cw  = W - mg * 2

  const logoB64   = logo ? await loadImg(logo) : null
  const fileShort = fileName.length > 55 ? fileName.slice(0, 52) + '…' : fileName
  const ctx       = { W, H, mg, cw, logo: logoB64, fileShort }

  // Cover
  drawCover(doc, { ...ctx, file: fileShort, score: credibilityScore, label: credibilityLabel, scoreColor: credibilityColor, items: summaryItems })

  // Category reference
  drawCategories(doc, ctx)

  // Claims — grouped by source
  doc.addPage()
  header(doc, ctx)
  let y = 32

  const newPage = () => { doc.addPage(); header(doc, ctx); y = 32 }
  const guard   = (need) => { if (y + need > H - 20) newPage() }

  const groups = {}
  claims.forEach(c => {
    const key = c.authorLine || 'Unknown Source'
    if (!groups[key]) groups[key] = []
    groups[key].push(c)
  })

  let first = true
  Object.entries(groups).forEach(([paper, grpClaims]) => {
    guard(24)
    if (!first) y += 8
    first = false

    f(doc, 10, 'bold', NAVY)
    const pLines = doc.splitTextToSize(paper, cw)
    doc.text(pLines[0], mg, y)
    hline(doc, mg, y + 4, W - mg, NAVY, 0.5)
    y += 13

    grpClaims.forEach(claim => {
      const statusLabel = statusConfig[claim.status]?.label || claim.status
      const textW  = cw - 16
      const qL = doc.splitTextToSize(`“${claim.text}”`, textW)
      const rL = doc.splitTextToSize(claim.reasoning || '', textW)
      const wL = claim.warning ? doc.splitTextToSize(claim.warning, textW) : []
      let bh = 10 + qL.length * 5.5 + 5 + rL.length * 5 + 5 + 10
      if (claim.authorLine) bh += 6
      if (claim.doi)        bh += 5.5
      if (wL.length)        bh += wL.length * 5 + 4
      guard(bh + 5)
      y = drawClaim(doc, { claim, statusLabel, mg, cw, W, y })
    })
  })

  // Footers (all pages except cover)
  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 2; i <= totalPages; i++) {
    doc.setPage(i)
    footer(doc, { W, H, mg, cw, pg: i - 1, total: totalPages - 1 })
  }

  doc.save(`verifai_report_${fileName.replace(/\.pdf$/i, '')}.pdf`)
}
