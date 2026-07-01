import jsPDF from 'jspdf'

// ─── Palette ─────────────────────────────────────────────────────────────────
const C = {
  navy:   [15,  40,  80],
  ink:    [28,  30,  34],
  body:   [60,  63,  70],
  subtle: [120, 124, 132],
  rule:   [220, 222, 228],
  bg:     [248, 249, 251],
  white:  [255, 255, 255],
}

const STATUS_COLORS = {
  supported:    '#16a34a',
  partial:      '#ca8a04',
  unsupported:  '#dc2626',
  hallucinated: '#7c3aed',
  insufficient: '#6b7280',
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function hex2rgb(hex) {
  const h = (hex || '#888').replace('#', '')
  const n = parseInt(h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function loadImg(url) {
  return new Promise((res) => {
    const img = new window.Image()
    img.crossOrigin = 'Anonymous'
    img.onload = () => {
      const c = document.createElement('canvas')
      c.width = img.width; c.height = img.height
      c.getContext('2d').drawImage(img, 0, 0)
      res(c.toDataURL('image/png'))
    }
    img.onerror = () => res(null)
    img.src = url
  })
}

// Typography helper: font / size / color in one call
function t(doc, size, weight, color) {
  doc.setFont('helvetica', weight || 'normal')
  doc.setFontSize(size)
  doc.setTextColor(...(color || C.ink))
}

// Horizontal rule
function rule(doc, x1, y, x2, color, w) {
  doc.setDrawColor(...(color || C.rule))
  doc.setLineWidth(w || 0.3)
  doc.line(x1, y, x2, y)
}

// ─── Running header (all pages except cover) ──────────────────────────────────

function pageHeader(doc, { W, mg, logo, date }) {
  doc.setFillColor(...C.white)
  doc.rect(0, 0, W, 24, 'F')
  if (logo) doc.addImage(logo, 'PNG', mg, 5, 12, 12)
  const lx = logo ? mg + 16 : mg
  t(doc, 9.5, 'bold', C.navy);  doc.text('verifAi', lx, 13)
  t(doc, 7,   'normal', C.subtle)
  doc.text(`Verification Report  ·  ${date}`, lx, 20)
  rule(doc, mg, 24, W - mg)
}

// ─── Running footer ───────────────────────────────────────────────────────────

function pageFooter(doc, { W, H, mg, cw, pg, total }) {
  rule(doc, mg, H - 16, W - mg)
  t(doc, 6.5, 'italic', C.subtle)
  doc.text(
    'VerifAi uses AI-assisted analysis. Results may contain errors — always verify critical claims against original sources.',
    mg, H - 10, { maxWidth: cw - 30 }
  )
  t(doc, 7, 'normal', C.subtle)
  doc.text(`${pg} / ${total}`, W - mg, H - 10, { align: 'right' })
}

// ─── Cover page ───────────────────────────────────────────────────────────────

function cover(doc, { W, H, mg, cw, logo, file, score, label, scoreColor, items, date }) {
  // Top stripe — full width, deep navy
  doc.setFillColor(...C.navy)
  doc.rect(0, 0, W, 52, 'F')

  // Brand
  if (logo) doc.addImage(logo, 'PNG', mg, 12, 16, 16)
  const bx = logo ? mg + 20 : mg
  t(doc, 16, 'bold', C.white);        doc.text('verifAi', bx, 23)
  t(doc, 8,  'normal', [160,185,215]);doc.text('AI-Powered Citation Verification', bx, 31)

  // Report title below stripe
  t(doc, 8, 'bold', [160,185,215]);   doc.text('VERIFICATION REPORT', mg, 43)

  // File name — truncated
  const short = file.length > 70 ? file.slice(0, 67) + '…' : file
  t(doc, 8, 'normal', [200,215,235]); doc.text(short, mg, 50)

  let y = 70

  // ── Score block ───────────────────────────────────────────────────────────
  const [sr, sg, sb] = hex2rgb(scoreColor)
  t(doc, 7, 'bold', C.subtle); doc.text('CREDIBILITY SCORE', mg, y)
  y += 7

  t(doc, 36, 'bold', [sr, sg, sb])
  doc.text(`${score.toFixed(1)}%`, mg, y + 18)
  t(doc, 11, 'bold', [sr, sg, sb])
  doc.text(label, mg, y + 27)

  // Stacked bar (right half of page)
  const total = items.reduce((s, i) => s + i.count, 0)
  const bw = cw * 0.42, bstart = mg + cw * 0.53
  doc.setFillColor(...C.rule)
  doc.roundedRect(bstart, y + 4, bw, 4, 2, 2, 'F')
  let cx = bstart
  items.forEach(item => {
    const sw = total > 0 ? (item.count / total) * bw : 0
    if (sw > 0) {
      doc.setFillColor(...hex2rgb(item.color)); doc.rect(cx, y + 4, sw, 4, 'F'); cx += sw
    }
  })

  // Legend
  let ly = y + 13
  items.forEach((item, i) => {
    const col = i % 2, row = Math.floor(i / 2)
    const lx = bstart + col * (bw / 2), _ly = ly + row * 7
    doc.setFillColor(...hex2rgb(item.color)); doc.circle(lx + 2, _ly - 1.5, 1.5, 'F')
    t(doc, 7.5, 'normal', C.body); doc.text(item.label, lx + 6, _ly)
    t(doc, 7.5, 'bold',   C.ink);  doc.text(String(item.count), lx + bw / 2 - 2, _ly, { align: 'right' })
  })

  y += 46
  rule(doc, mg, y, mg + cw)
  y += 10

  // ── Stats row ─────────────────────────────────────────────────────────────
  const stats = [
    { v: String(total), l: 'Total claims analysed' },
    { v: date, l: 'Report generated' },
    { v: 'Llama 4 · RAG', l: 'Powered by' },
  ]
  const sw = cw / stats.length
  stats.forEach((s, i) => {
    const sx = mg + i * sw
    t(doc, 12, 'bold', C.navy); doc.text(s.v, sx, y + 9)
    t(doc, 7,  'normal', C.subtle); doc.text(s.l, sx, y + 17)
    if (i < stats.length - 1) rule(doc, sx + sw - 4, y, sx + sw - 4, y + 22, C.rule, 0.3)
  })

  y += 28
  rule(doc, mg, y, mg + cw)
  y += 10

  // ── How it works ──────────────────────────────────────────────────────────
  t(doc, 9, 'bold', C.navy); doc.text('How it works', mg, y); y += 9

  const steps = [
    'PDF uploaded and text extracted from the research paper.',
    'Citations and references identified; DOIs resolved via CrossRef and OpenAlex.',
    'Claims linked to each citation extracted using the Llama 4 language model.',
    'Source documents retrieved and compared semantically via RAG pipeline.',
    'Each claim assigned a verdict and confidence score.',
  ]
  steps.forEach((step, i) => {
    // circle number
    doc.setFillColor(...C.navy); doc.circle(mg + 3.5, y - 1.5, 3.5, 'F')
    t(doc, 7, 'bold', C.white);  doc.text(String(i + 1), mg + 3.5, y - 0.5, { align: 'center' })
    t(doc, 8, 'normal', C.body); doc.text(step, mg + 11, y)
    y += 9
  })

  y += 4
  rule(doc, mg, y, mg + cw)
  y += 8

  // ── Disclaimer ────────────────────────────────────────────────────────────
  t(doc, 7.5, 'italic', C.subtle)
  const disc = doc.splitTextToSize(
    'Disclaimer: VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors and accuracy is not guaranteed — please verify critical claims against the original sources before drawing conclusions.',
    cw
  )
  doc.text(disc, mg, y)
}

// ─── Category reference page ─────────────────────────────────────────────────

function categoryPage(doc, { W, H, mg, cw, logo, date }) {
  doc.addPage()
  pageHeader(doc, { W, mg, logo, date })
  let y = 33

  t(doc, 10, 'bold', C.navy); doc.text('Verdict Category Reference', mg, y)
  rule(doc, mg, y + 3, mg + cw, C.navy, 0.5)
  y += 13

  const cats = [
    {
      key: 'Supported',  color: '#16a34a',
      desc: 'The AI found text in the cited source that clearly confirms the claim. A valid DOI was resolved, similarity ≥ 0.50, and the model confirmed the match.',
      note: 'Strongest indicator of citation accuracy.',
    },
    {
      key: 'Partially Supported', color: '#ca8a04',
      desc: 'The source addresses the same topic but does not fully confirm all aspects. Common causes: paraphrasing that overstates results, missing caveats, or combined findings.',
      note: 'Review the specific discrepancy in the AI reasoning below the claim.',
    },
    {
      key: 'Unsupported', color: '#dc2626',
      desc: 'The source was retrieved and read, but the claim contradicts or is absent from the source content. Distinct from Insufficient Evidence: the evidence exists but does not back the claim.',
      note: 'Consider revising or removing this claim.',
    },
    {
      key: 'Hallucinated', color: '#7c3aed',
      desc: 'The DOI in the citation is invalid or does not resolve to any existing publication. Assigned by a deterministic rule — not by the AI. The source may be fabricated.',
      note: 'Strongest signal of a fabricated citation.',
    },
    {
      key: 'Insufficient Evidence', color: '#6b7280',
      desc: 'Not enough accessible text was retrieved. Causes: paywalled source, abstract-only retrieval, similarity below threshold, or a malformed model response.',
      note: 'Upload the source PDF manually on the results page to enable full re-verification.',
    },
  ]

  cats.forEach(cat => {
    const [cr, cg, cb] = hex2rgb(cat.color)
    const dLines = doc.splitTextToSize(cat.desc, cw - 10)
    const nLines = doc.splitTextToSize(`Note: ${cat.note}`, cw - 10)
    const bh = 8 + dLines.length * 5 + nLines.length * 4.5 + 7

    if (y + bh > H - 22) {
      doc.addPage(); pageHeader(doc, { W, mg, logo, date }); y = 33
    }

    // Left accent bar (thin line, not a fat filled rect)
    doc.setFillColor(cr, cg, cb); doc.rect(mg, y, 2, bh, 'F')

    // Status label
    t(doc, 9, 'bold', [cr, cg, cb]); doc.text(cat.key, mg + 7, y + 7)

    // Description
    t(doc, 8, 'normal', C.body); doc.text(dLines, mg + 7, y + 13)

    // Note (italic, same accent color)
    t(doc, 7.5, 'italic', C.subtle)
    doc.text(nLines, mg + 7, y + 13 + dLines.length * 5 + 3)

    rule(doc, mg, y + bh, mg + cw, C.rule, 0.2)
    y += bh + 7
  })
}

// ─── Claims pages ─────────────────────────────────────────────────────────────

function claimBlock(doc, { claim, config, mg, cw, W, y }) {
  const statusColor = STATUS_COLORS[claim.status] || '#888'
  const [sr, sg, sb] = hex2rgb(statusColor)

  const quoteLines  = doc.splitTextToSize(`"${claim.text}"`, cw - 8)
  const reasonLines = doc.splitTextToSize(claim.reasoning || '', cw - 8)
  const warnLines   = claim.warning ? doc.splitTextToSize(claim.warning, cw - 8) : []

  const conf = Math.round((claim.confidence || 0) * 100)

  let h = 7 + quoteLines.length * 5 + 5 + reasonLines.length * 4.5 + 9
  if (claim.authorLine) h += 5.5
  if (claim.doi)        h += 5
  if (warnLines.length) h += warnLines.length * 4.5 + 4

  const sy = y

  // Left status bar
  doc.setFillColor(sr, sg, sb); doc.rect(mg, sy, 2, h, 'F')

  // Claim index
  t(doc, 7, 'bold', C.subtle); doc.text(`CLAIM ${claim.displayId}`, mg + 7, sy + 6)

  // Status badge (right-aligned, text only — no filled pill)
  t(doc, 7.5, 'bold', [sr, sg, sb])
  doc.text(config.label, W - mg, sy + 6, { align: 'right' })

  let iy = sy + 12

  // Claim text — italic quote
  t(doc, 8.5, 'italic', C.ink)
  doc.text(quoteLines, mg + 7, iy); iy += quoteLines.length * 5 + 4

  // Source meta
  if (claim.authorLine) {
    t(doc, 7, 'normal', C.subtle)
    doc.text(`Source: ${claim.authorLine}`, mg + 7, iy); iy += 5.5
  }
  if (claim.doi) {
    t(doc, 7, 'normal', [37, 99, 235])
    doc.text(`DOI: ${claim.doi}`, mg + 7, iy); iy += 5
  }

  // Reasoning — indented, smaller, muted
  t(doc, 7.5, 'normal', C.subtle)
  doc.text(reasonLines, mg + 7, iy); iy += reasonLines.length * 4.5 + 3

  // Warning
  if (warnLines.length) {
    t(doc, 7, 'italic', [160, 80, 10])
    doc.text(warnLines, mg + 7, iy); iy += warnLines.length * 4.5 + 3
  }

  // Confidence — inline text bar
  const barX = mg + 7, barW = 38
  t(doc, 6.5, 'normal', C.subtle); doc.text('Confidence', barX, iy + 3)
  doc.setFillColor(...C.rule)
  doc.roundedRect(barX + 24, iy, barW, 2.5, 1, 1, 'F')
  const cHex = conf > 70 ? '#16a34a' : conf > 40 ? '#ca8a04' : '#dc2626'
  doc.setFillColor(...hex2rgb(cHex))
  doc.roundedRect(barX + 24, iy, Math.max(barW * (conf / 100), 1.5), 2.5, 1, 1, 'F')
  t(doc, 6.5, 'normal', C.subtle); doc.text(`${conf}%`, barX + 24 + barW + 3, iy + 3)

  // Thin bottom rule
  rule(doc, mg, sy + h, mg + cw, C.rule, 0.2)

  return sy + h + 6
}

// ─── Main export ─────────────────────────────────────────────────────────────

export async function generateVerificationPdf({
  claims, statusConfig, summaryItems, fileName, logo,
  credibilityScore = 0, credibilityLabel = 'Unknown', credibilityColor = '#888888',
}) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  const W  = doc.internal.pageSize.getWidth()
  const H  = doc.internal.pageSize.getHeight()
  const mg = 16
  const cw = W - mg * 2

  const logoB64 = logo ? await loadImg(logo) : null
  const date    = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
  const ctx     = { W, H, mg, cw, logo: logoB64, date }

  // Cover
  cover(doc, { ...ctx, file: fileName, score: credibilityScore, label: credibilityLabel, scoreColor: credibilityColor, items: summaryItems })

  // Category reference
  categoryPage(doc, ctx)

  // ── Claims ────────────────────────────────────────────────────────────────
  doc.addPage()
  pageHeader(doc, ctx)
  let y = 33

  const newPage = () => { doc.addPage(); pageHeader(doc, ctx); y = 33 }
  const guard   = (need) => { if (y + need > H - 22) newPage() }

  // Group by source
  const groups = {}
  claims.forEach(c => {
    const key = c.authorLine || 'Unknown Source'
    if (!groups[key]) groups[key] = []
    groups[key].push(c)
  })

  let firstGroup = true
  Object.entries(groups).forEach(([paper, groupClaims]) => {
    guard(16)
    if (!firstGroup) y += 4
    firstGroup = false

    // Section heading — simple bold text + rule, no filled band
    t(doc, 9, 'bold', C.navy); doc.text(paper, mg, y)
    rule(doc, mg, y + 3, mg + cw, C.navy, 0.5)
    y += 12

    groupClaims.forEach(claim => {
      const config = statusConfig[claim.status] || { label: claim.status, color: '#888', bg: '#eee' }

      // Estimate block height to decide page break
      const qLines = doc.splitTextToSize(`"${claim.text}"`, cw - 8)
      const rLines = doc.splitTextToSize(claim.reasoning || '', cw - 8)
      const wLines = claim.warning ? doc.splitTextToSize(claim.warning, cw - 8) : []
      let bh = 7 + qLines.length * 5 + 5 + rLines.length * 4.5 + 9
      if (claim.authorLine) bh += 5.5
      if (claim.doi)        bh += 5
      if (wLines.length)    bh += wLines.length * 4.5 + 4
      guard(bh + 6)

      y = claimBlock(doc, { claim, config, mg, cw, W, y })
    })
  })

  // Footers (skip cover = page 1)
  const total = doc.internal.getNumberOfPages()
  for (let i = 2; i <= total; i++) {
    doc.setPage(i)
    pageFooter(doc, { W, H, mg, cw, pg: i - 1, total: total - 1 })
  }

  doc.save(`verifai_report_${fileName.replace(/\.pdf$/i, '')}.pdf`)
}
