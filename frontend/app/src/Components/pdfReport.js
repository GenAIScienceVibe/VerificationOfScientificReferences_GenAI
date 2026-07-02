import jsPDF from 'jspdf'

const INK = [20, 22, 26]
const BODY = [45, 48, 55]
const MUTED = [95, 99, 108]
const RULE = [215, 219, 226]

const STATUS = {
  supported: { label: 'Supported', color: [22, 130, 70] },
  partial: { label: 'Partially supported', color: [180, 110, 4] },
  partially_supported: { label: 'Partially supported', color: [180, 110, 4] },
  unsupported: { label: 'Unsupported', color: [190, 35, 35] },
  hallucinated: { label: 'Hallucinated', color: [110, 45, 190] },
  insufficient: { label: 'Insufficient Evidence', color: [95, 100, 110] },
  insufficient_evidence: { label: 'Insufficient Evidence', color: [95, 100, 110] },
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

function stripOuterQuotes(text) {
  let t = clean(text)
  while (
    (t.startsWith('"') && t.endsWith('"')) ||
    (t.startsWith('“') && t.endsWith('”'))
  ) {
    t = t.slice(1, -1).trim()
  }
  return t
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

function formatDate() {
  const d = new Date()
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
}

function writeWrapped(doc, text, x, y, width, lineHeight = 4.8) {
  const lines = doc.splitTextToSize(clean(text), width)
  doc.text(lines, x, y)
  return y + lines.length * lineHeight
}

function rule(doc, x1, y, x2) {
  doc.setDrawColor(...RULE)
  doc.setLineWidth(0.35)
  doc.line(x1, y, x2, y)
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
      text: stripOuterQuotes(
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
      status: normalizeStatus(
        claim?.status ||
        claim?.verification_status ||
        claim?.result ||
        claim?.label ||
        claim?.category ||
        'insufficient'
      ),
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

function countClaims(claims) {
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

function drawHeader(doc, layout, fileName) {
  const { pageW, margin } = layout

  font(doc, 18, 'bold', INK)
  doc.text('verifAi', margin, 18)

  font(doc, 9, 'normal', MUTED)
  doc.text(`Verification Report · ${fileName} · ${formatDate()}`, margin, 28, {
    maxWidth: pageW - margin * 2,
  })

  rule(doc, margin, 38, pageW - margin)
}

function drawFooter(doc, layout, page, total) {
  const { pageW, pageH, margin } = layout

  rule(doc, margin, pageH - 22, pageW - margin)

  font(doc, 7.3, 'normal', MUTED)
  doc.text(
    'VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors and accuracy is not guaranteed to be 100% — please verify critical claims against the original sources.',
    margin,
    pageH - 15,
    { maxWidth: pageW - margin * 2 - 28 }
  )

  font(doc, 8, 'normal', MUTED)
  doc.text(`Page ${page} / ${total}`, pageW - margin, pageH - 9, { align: 'right' })
}

function ensureSpace(doc, y, needed, layout, fileName) {
  if (y + needed <= layout.pageH - 30) return y

  doc.addPage()
  drawHeader(doc, layout, fileName)
  return 50
}

function estimateClaimHeight(doc, claim, layout) {
  const w = layout.contentW
  const citation = claim.authorLine ? ` (${claim.authorLine})` : ''
  const quoteLines = doc.splitTextToSize(`"${claim.text}"${citation}`, w)
  const reasoningLines = doc.splitTextToSize(`AI reasoning: ${claim.reasoning || 'No reasoning provided.'}`, w)
  const warningText =
    claim.warning ||
    (claim.status === 'supported'
      ? ''
      : 'Human review recommended - this result may need manual verification.')
  const warningLines = warningText ? doc.splitTextToSize(warningText, w) : []

  return 15 + quoteLines.length * 4.8 + reasoningLines.length * 4.8 + warningLines.length * 4.8 + 14
}

function drawSummary(doc, y, counts, layout) {
  const { margin, contentW } = layout

  font(doc, 14, 'bold', INK)
  doc.text('Fazit — Claims Summary', margin, y)
  y += 9

  font(doc, 10, 'normal', INK)

  const leftX = margin
  const rightX = margin + contentW / 2 + 8
  const valueLeft = margin + contentW / 2 - 8
  const valueRight = margin + contentW

  doc.text('Supported', leftX, y)
  doc.text(String(counts.supported), valueLeft, y, { align: 'right' })
  doc.text('Partially supported', rightX, y)
  doc.text(String(counts.partial), valueRight, y, { align: 'right' })

  y += 7
  doc.text('Unsupported', leftX, y)
  doc.text(String(counts.unsupported), valueLeft, y, { align: 'right' })
  doc.text('Hallucinated', rightX, y)
  doc.text(String(counts.hallucinated), valueRight, y, { align: 'right' })

  y += 7
  doc.text('Insufficient evidence', leftX, y)
  doc.text(String(counts.insufficient), valueLeft, y, { align: 'right' })

  return y + 14
}

function drawClaim(doc, y, claim, index, layout, fileName) {
  const { margin, contentW, pageW } = layout
  const needed = estimateClaimHeight(doc, claim, layout)
  y = ensureSpace(doc, y, needed, layout, fileName)

  const info = statusInfo(claim.status)

  font(doc, 8.8, 'bold', INK)
  doc.text('CLAIM', margin, y)

  font(doc, 8.8, 'bold', MUTED)
  doc.text(claim.id || `result_${index}`, margin + 22, y, {
    maxWidth: contentW - 70,
  })

  font(doc, 8.8, 'bold', info.color)
  doc.text(info.label, pageW - margin, y, { align: 'right' })

  y += 8

  const citation = claim.authorLine ? ` (${claim.authorLine})` : ''

  font(doc, 9.4, 'normal', INK)
  y = writeWrapped(doc, `"${claim.text}"${citation}`, margin, y, contentW, 4.8)
  y += 7

  font(doc, 8.8, 'normal', BODY)
  y = writeWrapped(
    doc,
    `AI reasoning: ${claim.reasoning || 'No reasoning provided.'}`,
    margin,
    y,
    contentW,
    4.8
  )
  y += 5

  const warning =
    claim.warning ||
    (claim.status === 'supported'
      ? ''
      : 'Human review recommended - this result may need manual verification.')

  if (warning) {
    font(doc, 8.8, 'normal', BODY)
    y = writeWrapped(doc, warning, margin, y, contentW, 4.8)
    y += 5
  }

  if (claim.doi) {
    font(doc, 8, 'normal', MUTED)
    y = writeWrapped(doc, `DOI: ${claim.doi}`, margin, y, contentW, 4.6)
    y += 3
  }

  font(doc, 8.8, 'normal', INK)
  doc.text(`Confidence ${claim.confidence}`, margin, y)

  return y + 12
}

function buildReport(...args) {
  const { raw, fileName } = inputFromArgs(args)
  const claims = getClaims(raw)
  const score = getScore(raw, claims)
  const summary = countClaims(claims)

  const doc = new jsPDF('p', 'mm', 'a4')
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 17
  const contentW = pageW - margin * 2
  const layout = { pageW, pageH, margin, contentW }

  drawHeader(doc, layout, fileName)

  let y = 52

  font(doc, 13, 'bold', INK)
  doc.text(`Credibility Score: ${score}% — ${scoreLabel(score)}`, margin, y)
  y += 8

  font(doc, 9.5, 'normal', INK)
  y = writeWrapped(doc, scoreExplanation(score), margin, y, contentW, 4.8)
  y += 12

  y = drawSummary(doc, y, summary, layout)

  font(doc, 14, 'bold', INK)
  doc.text('Claims Overview', margin, y)
  y += 10

  if (!claims.length) {
    font(doc, 9.5, 'normal', MUTED)
    doc.text('No claims were available for this report.', margin, y)
  } else {
    claims.forEach((claim, index) => {
      y = drawClaim(doc, y, claim, index + 1, layout, fileName)
    })
  }

  const totalPages = doc.internal.getNumberOfPages()
  for (let page = 1; page <= totalPages; page += 1) {
    doc.setPage(page)
    drawFooter(doc, layout, page, totalPages)
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
