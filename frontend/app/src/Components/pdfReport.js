import jsPDF from 'jspdf'

const NAVY = [15, 45, 88]
const INK = [28, 30, 36]
const BODY = [55, 58, 66]
const MUTED = [115, 120, 130]
const LIGHT = [218, 222, 228]
const CARD = [248, 250, 252]
const WHITE = [255, 255, 255]

const STATUS = {
  supported: { label: 'Supported', color: [22, 163, 74] },
  partial: { label: 'Partially supported', color: [226, 132, 7] },
  partially_supported: { label: 'Partially supported', color: [226, 132, 7] },
  unsupported: { label: 'Unsupported', color: [220, 38, 38] },
  hallucinated: { label: 'Hallucinated', color: [112, 39, 195] },
  insufficient: { label: 'Insufficient Evidence', color: [105, 114, 128] },
  insufficient_evidence: { label: 'Insufficient Evidence', color: [105, 114, 128] },
}

function font(doc, size, style = 'normal', color = INK) {
  doc.setFont('helvetica', style)
  doc.setFontSize(size)
  doc.setTextColor(...color)
}

function clean(value) {
  if (value === null || value === undefined) return ''
  return String(value).replace(/\s+/g, ' ').trim()
}

function normalizeStatus(value) {
  const s = clean(value).toLowerCase().replace(/[\s-]+/g, '_')
  if (STATUS[s]) return s
  if (s.includes('partial')) return 'partial'
  if (s.includes('hallucinated')) return 'hallucinated'
  if (s.includes('unsupported')) return 'unsupported'
  if (s.includes('insufficient')) return 'insufficient'
  if (s.includes('support')) return 'supported'
  return 'insufficient'
}

function statusInfo(status) {
  return STATUS[normalizeStatus(status)] || STATUS.insufficient
}

function writeWrapped(doc, text, x, y, width, lineHeight = 5) {
  const lines = doc.splitTextToSize(clean(text), width)
  doc.text(lines, x, y)
  return y + lines.length * lineHeight
}

function dateString() {
  const d = new Date()
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
}

function getFileName(input, fallback) {
  return clean(
    input?.fileName ||
    input?.filename ||
    input?.documentName ||
    input?.document_name ||
    input?.originalFileName ||
    input?.original_filename ||
    input?.paperName ||
    input?.paper_name ||
    input?.upload?.filename ||
    input?.document?.filename ||
    fallback ||
    'uploaded_document.pdf'
  )
}

function toArray(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'object') return Object.values(value)
  return []
}

function getClaims(input) {
  const possible =
    input?.claims ||
    input?.results ||
    input?.verificationResults ||
    input?.verification_results ||
    input?.claimResults ||
    input?.claim_results ||
    input?.data?.claims ||
    input?.data?.results ||
    input?.workflow?.claims ||
    input?.workflow?.results ||
    []

  return toArray(possible).map((claim, index) => {
    const status = normalizeStatus(
      claim?.status ||
      claim?.verification_status ||
      claim?.result ||
      claim?.label ||
      claim?.category ||
      'insufficient'
    )

    const rawConfidence =
      claim?.confidence ??
      claim?.confidence_score ??
      claim?.score ??
      0

    const number = Number(rawConfidence)
    const confidence = Number.isFinite(number)
      ? number <= 1
        ? Math.round(number * 100)
        : Math.round(number)
      : 0

    return {
      id: clean(
        claim?.id ||
        claim?.claim_id ||
        claim?.claimId ||
        claim?.result_id ||
        claim?.resultId ||
        `result_${String(index + 1).padStart(2, '0')}`
      ),
      text: clean(
        claim?.text ||
        claim?.claim ||
        claim?.claim_text ||
        claim?.statement ||
        claim?.content ||
        claim?.sentence ||
        ''
      ),
      reasoning: clean(
        claim?.reasoning ||
        claim?.ai_reasoning ||
        claim?.aiReasoning ||
        claim?.explanation ||
        claim?.reason ||
        claim?.evidence ||
        claim?.summary ||
        ''
      ),
      warning: clean(
        claim?.warning ||
        claim?.human_review ||
        claim?.review_note ||
        claim?.note ||
        ''
      ),
      authorLine: clean(
        claim?.authorLine ||
        claim?.author_line ||
        claim?.citation ||
        claim?.source ||
        claim?.reference ||
        ''
      ),
      doi: clean(claim?.doi || claim?.DOI || ''),
      status,
      confidence,
    }
  })
}

function getScore(input, claims) {
  const raw =
    input?.credibilityScore ??
    input?.credibility_score ??
    input?.score ??
    input?.overallScore ??
    input?.overall_score ??
    input?.summary?.credibilityScore ??
    input?.summary?.credibility_score

  const n = Number(raw)
  if (Number.isFinite(n)) return n <= 1 ? Math.round(n * 100) : Math.round(n)

  if (!claims.length) return 0

  const points = claims.reduce((sum, claim) => {
    if (claim.status === 'supported') return sum + 1
    if (claim.status === 'partial' || claim.status === 'partially_supported') return sum + 0.5
    return sum
  }, 0)

  return Math.round((points / claims.length) * 100)
}

function scoreLabel(score) {
  if (score >= 85) return 'Reliable'
  if (score >= 60) return 'Partially Reliable'
  if (score >= 35) return 'Low Reliability'
  return 'Not Reliable'
}

function scoreExplanation(score) {
  if (score >= 85) return 'Most claims appear to be supported by their cited sources.'
  if (score >= 60) return 'Some claims are inaccurate or unsupported by their cited sources.'
  if (score >= 35) return 'Several claims are unsupported or require manual verification.'
  return 'Most claims require manual verification against the original sources.'
}

function counts(claims) {
  return {
    supported: claims.filter(c => c.status === 'supported').length,
    partial: claims.filter(c => c.status === 'partial' || c.status === 'partially_supported').length,
    unsupported: claims.filter(c => c.status === 'unsupported').length,
    hallucinated: claims.filter(c => c.status === 'hallucinated').length,
    insufficient: claims.filter(c => c.status === 'insufficient' || c.status === 'insufficient_evidence').length,
  }
}

function inputFromArgs(args) {
  const first = args[0] || {}
  const second = args[1]

  if (Array.isArray(first)) {
    return {
      raw: { claims: first, fileName: second },
      fileName: clean(second || 'uploaded_document.pdf'),
    }
  }

  return {
    raw: first,
    fileName: getFileName(first, second),
  }
}

function drawRule(doc, x1, y, x2) {
  doc.setDrawColor(...LIGHT)
  doc.setLineWidth(0.35)
  doc.line(x1, y, x2, y)
}

function drawLogoMark(doc, x, y) {
  font(doc, 7, 'normal', NAVY)
  doc.text('verif', x, y + 4.2)

  doc.setDrawColor(54, 132, 210)
  doc.setLineWidth(0.65)
  const cx = x + 13
  const cy = y + 2.6
  for (let i = 0; i < 12; i += 1) {
    const a = (Math.PI * 2 * i) / 12
    const r1 = 2.1
    const r2 = 4.1
    doc.line(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1, cx + Math.cos(a) * r2, cy + Math.sin(a) * r2)
  }
}

function header(doc, layout, fileName) {
  const { pageW, margin } = layout

  drawLogoMark(doc, margin + 5, 15)

  font(doc, 17, 'bold', NAVY)
  doc.text('verifAi', margin + 30, 21)

  font(doc, 8.5, 'normal', MUTED)
  doc.text(`Verification Report  ·  ${fileName}  ·  ${dateString()}`, margin + 30, 31, {
    maxWidth: pageW - margin * 2 - 30,
  })

  drawRule(doc, margin, 43, pageW - margin)
}

function footer(doc, layout, page, total) {
  const { pageW, pageH, margin } = layout

  drawRule(doc, margin, pageH - 26, pageW - margin)

  font(doc, 7.5, 'italic', MUTED)
  doc.text(
    'VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors and accuracy is not guaranteed to be 100% — please verify critical claims against the original sources.',
    margin,
    pageH - 17,
    { maxWidth: pageW - margin * 2 - 35 }
  )

  font(doc, 8, 'normal', MUTED)
  doc.text(`Page ${page} / ${total}`, pageW - margin, pageH - 15, { align: 'right' })
}

function ensurePage(doc, y, needed, layout, fileName) {
  if (y + needed <= layout.pageH - 34) return y

  doc.addPage()
  header(doc, layout, fileName)
  return 57
}

function roundedCard(doc, x, y, w, h, fill = WHITE, stroke = LIGHT) {
  doc.setFillColor(...fill)
  doc.setDrawColor(...stroke)
  doc.setLineWidth(0.55)
  doc.roundedRect(x, y, w, h, 4, 4, 'FD')
}

function scoreCard(doc, y, score, layout) {
  const { margin, contentW } = layout
  const h = 33

  roundedCard(doc, margin, y, contentW, h, CARD, LIGHT)

  font(doc, 14, 'bold', NAVY)
  doc.text(`Credibility Score: ${score}% — ${scoreLabel(score)}`, margin + 8, y + 15)

  font(doc, 9.5, 'normal', MUTED)
  doc.text(scoreExplanation(score), margin + 8, y + 25, { maxWidth: contentW - 16 })

  return y + h + 14
}

function summaryCard(doc, y, c, layout) {
  const { margin, contentW } = layout
  const h = 71

  roundedCard(doc, margin, y, contentW, h, WHITE, LIGHT)

  font(doc, 12.5, 'bold', INK)
  doc.text('Fazit — Claims Summary', margin + 8, y + 14)

  const items = [
    ['Supported', c.supported, STATUS.supported.color],
    ['Partially supported', c.partial, STATUS.partial.color],
    ['Unsupported', c.unsupported, STATUS.unsupported.color],
    ['Hallucinated', c.hallucinated, STATUS.hallucinated.color],
    ['Insufficient evidence', c.insufficient, STATUS.insufficient.color],
  ]

  const leftX = margin + 8
  const rightX = margin + contentW / 2 + 6
  const valueLeft = margin + contentW / 2 - 10
  const valueRight = margin + contentW - 13

  items.forEach((item, i) => {
    const col = i % 2
    const row = Math.floor(i / 2)
    const x = col === 0 ? leftX : rightX
    const vx = col === 0 ? valueLeft : valueRight
    const yy = y + 27 + row * 10

    doc.setFillColor(...item[2])
    doc.circle(x + 2, yy - 1.8, 1.7, 'F')

    font(doc, 9.5, 'normal', BODY)
    doc.text(item[0], x + 7, yy)

    font(doc, 9.5, 'bold', INK)
    doc.text(String(item[1]), vx, yy, { align: 'right' })
  })

  const total = Object.values(c).reduce((s, n) => s + n, 0)
  const barX = margin + 8
  const barY = y + 54
  const barW = contentW - 16
  const barH = 5

  doc.setFillColor(210, 214, 220)
  doc.rect(barX, barY, barW, barH, 'F')

  let bx = barX
  items.forEach(item => {
    const width = total ? (item[1] / total) * barW : 0
    if (width > 0) {
      doc.setFillColor(...item[2])
      doc.rect(bx, barY, width, barH, 'F')
      bx += width
    }
  })

  return y + h + 12
}

function claimHeight(doc, claim, layout) {
  const textW = layout.contentW - 22
  const quote = `"${claim.text}"${claim.authorLine ? ` (${claim.authorLine})` : ''}`
  const qLines = doc.splitTextToSize(quote, textW)
  const rLines = doc.splitTextToSize(`AI reasoning: ${claim.reasoning || 'No reasoning provided.'}`, textW)
  const wText = claim.warning || 'Human review recommended - this result may need manual verification.'
  const wLines = doc.splitTextToSize(wText, textW)

  return 34 + qLines.length * 4.9 + rLines.length * 4.9 + wLines.length * 4.9 + 22
}

function drawConfidence(doc, x, y, value, color) {
  font(doc, 8.5, 'normal', MUTED)
  doc.text('Confidence', x, y + 1.5)

  const barX = x + 35
  const barY = y - 1.8
  const barW = 45

  doc.setDrawColor(225, 226, 228)
  doc.setLineWidth(3)
  doc.setLineCap && doc.setLineCap('round')
  doc.line(barX, barY, barX + barW, barY)

  doc.setDrawColor(...color)
  doc.setLineWidth(3)
  const dotX = barX + Math.max(0, Math.min(100, value)) / 100 * barW
  doc.line(barX, barY, dotX, barY)

  doc.setFillColor(...color)
  doc.circle(dotX, barY, 1.5, 'F')

  font(doc, 8.5, 'normal', MUTED)
  doc.text(String(value), barX + barW + 8, y + 1.5)
}

function claimCard(doc, y, claim, index, layout, fileName) {
  const { margin, contentW, pageW } = layout
  let h = claimHeight(doc, claim, layout)
  y = ensurePage(doc, y, h, layout, fileName)

  const info = statusInfo(claim.status)
  const accent = info.color
  const cardX = margin
  const cardY = y
  const cardW = contentW

  roundedCard(doc, cardX, cardY, cardW, h, WHITE, [198, 205, 214])

  doc.setFillColor(...accent)
  doc.roundedRect(cardX, cardY, 4, h, 2, 2, 'F')

  font(doc, 8.5, 'bold', MUTED)
  doc.text(`CLAIM ${claim.id || `result_${index}`}`, cardX + 11, y + 13)

  const label = info.label
  const pillW = Math.max(30, doc.getTextWidth(label) + 12)
  doc.setFillColor(250, 250, 251)
  doc.roundedRect(pageW - margin - pillW - 8, y + 8, pillW, 9, 4, 4, 'F')
  font(doc, 8, 'bold', accent)
  doc.text(label, pageW - margin - 8 - pillW / 2, y + 14.2, { align: 'center' })

  y += 24

  const textW = cardW - 22
  const quote = `"${claim.text}"${claim.authorLine ? ` (${claim.authorLine})` : ''}`

  font(doc, 9.2, 'normal', INK)
  y = writeWrapped(doc, quote, cardX + 11, y, textW, 4.9)
  y += 11

  font(doc, 8.8, 'italic', BODY)
  y = writeWrapped(doc, `AI reasoning: ${claim.reasoning || 'No reasoning provided.'}`, cardX + 11, y, textW, 4.9)
  y += 8

  const warn = claim.warning || 'Human review recommended - this result may need manual verification.'
  font(doc, 8.8, 'normal', [222, 105, 0])
  y = writeWrapped(doc, warn, cardX + 11, y, textW, 4.9)
  y += 11

  drawConfidence(doc, cardX + 11, y, claim.confidence, accent)

  return cardY + h + 10
}

function buildReport(...args) {
  const { raw, fileName } = inputFromArgs(args)
  const claims = getClaims(raw)
  const score = getScore(raw, claims)
  const c = counts(claims)

  const doc = new jsPDF('p', 'mm', 'a4')
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 14
  const contentW = pageW - margin * 2
  const layout = { pageW, pageH, margin, contentW }

  header(doc, layout, fileName)

  let y = 55

  y = scoreCard(doc, y, score, layout)
  y = summaryCard(doc, y, c, layout)

  font(doc, 12.5, 'bold', INK)
  doc.text('Claims Overview', margin, y)
  y += 10

  if (!claims.length) {
    roundedCard(doc, margin, y, contentW, 28, WHITE, LIGHT)
    font(doc, 9.5, 'normal', MUTED)
    doc.text('No claims were available for this report.', margin + 8, y + 15)
  } else {
    claims.forEach((claim, index) => {
      y = claimCard(doc, y, claim, index + 1, layout, fileName)
    })
  }

  const totalPages = doc.internal.getNumberOfPages()
  for (let page = 1; page <= totalPages; page += 1) {
    doc.setPage(page)
    footer(doc, layout, page, totalPages)
  }

  const cleanName = fileName.replace(/\.pdf$/i, '').replace(/[^\w.-]+/g, '_')
  doc.save(`verifai_report_${cleanName}.pdf`)
  return doc
}

export function generateVerificationPdf(...args) {
  return buildReport(...args)
}

export function generateVerificationPDF(...args) {
  return buildReport(...args)
}

export function generatePdfReport(...args) {
  return buildReport(...args)
}

export function generatePDFReport(...args) {
  return buildReport(...args)
}

export function generateReport(...args) {
  return buildReport(...args)
}

export function downloadPdfReport(...args) {
  return buildReport(...args)
}

export function downloadPDFReport(...args) {
  return buildReport(...args)
}

export function createPdfReport(...args) {
  return buildReport(...args)
}

export default buildReport
