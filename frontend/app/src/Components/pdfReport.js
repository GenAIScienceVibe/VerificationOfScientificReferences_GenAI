import jsPDF from 'jspdf'

const INK = [20, 22, 26]
const MUTED = [75, 80, 88]
const LIGHT = [225, 228, 235]

const STATUS_CONFIG = {
  supported: { label: 'Supported', color: [22, 130, 70] },
  partial: { label: 'Partially supported', color: [180, 110, 4] },
  partially_supported: { label: 'Partially supported', color: [180, 110, 4] },
  unsupported: { label: 'Unsupported', color: [190, 35, 35] },
  hallucinated: { label: 'Hallucinated', color: [110, 45, 190] },
  insufficient: { label: 'Insufficient evidence', color: [95, 100, 110] },
  insufficient_evidence: { label: 'Insufficient evidence', color: [95, 100, 110] },
}

function setText(doc, size, style = 'normal', color = INK) {
  doc.setFont('helvetica', style)
  doc.setFontSize(size)
  doc.setTextColor(...color)
}

function line(doc, x1, y, x2) {
  doc.setDrawColor(...LIGHT)
  doc.setLineWidth(0.35)
  doc.line(x1, y, x2, y)
}

function cleanText(value) {
  if (value === null || value === undefined) return ''
  return String(value).replace(/\s+/g, ' ').trim()
}

function safeStatus(status) {
  const s = cleanText(status).toLowerCase().replace(/[\s-]+/g, '_')
  if (STATUS_CONFIG[s]) return s
  if (s.includes('partial')) return 'partial'
  if (s.includes('unsupported')) return 'unsupported'
  if (s.includes('hallucinated')) return 'hallucinated'
  if (s.includes('insufficient')) return 'insufficient'
  if (s.includes('support')) return 'supported'
  return 'insufficient'
}

function displayStatus(status) {
  const key = safeStatus(status)
  return STATUS_CONFIG[key]?.label || 'Insufficient evidence'
}

function statusColor(status) {
  const key = safeStatus(status)
  return STATUS_CONFIG[key]?.color || STATUS_CONFIG.insufficient.color
}

function formatDate(date = new Date()) {
  const month = date.getMonth() + 1
  const day = date.getDate()
  const year = date.getFullYear()
  return `${month}/${day}/${year}`
}

function fileNameFromInput(input, fallback) {
  return cleanText(
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

function arrayFromPossible(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'object') return Object.values(value)
  return []
}

function extractClaims(input) {
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

  return arrayFromPossible(possible).map((claim, index) => {
    const status = safeStatus(
      claim?.status ||
      claim?.verification_status ||
      claim?.result ||
      claim?.label ||
      claim?.category ||
      'insufficient'
    )

    const text =
      claim?.text ||
      claim?.claim ||
      claim?.claim_text ||
      claim?.statement ||
      claim?.content ||
      claim?.sentence ||
      ''

    const reasoning =
      claim?.reasoning ||
      claim?.ai_reasoning ||
      claim?.aiReasoning ||
      claim?.explanation ||
      claim?.reason ||
      claim?.evidence ||
      claim?.summary ||
      ''

    const warning =
      claim?.warning ||
      claim?.human_review ||
      claim?.review_note ||
      claim?.note ||
      ''

    const authorLine =
      claim?.authorLine ||
      claim?.author_line ||
      claim?.citation ||
      claim?.source ||
      claim?.reference ||
      ''

    const id =
      claim?.id ||
      claim?.claim_id ||
      claim?.claimId ||
      claim?.result_id ||
      claim?.resultId ||
      `result_${String(index + 1).padStart(2, '0')}`

    const confidenceRaw =
      claim?.confidence ??
      claim?.confidence_score ??
      claim?.score ??
      0

    const confidenceNumber = Number(confidenceRaw)
    const confidence = Number.isFinite(confidenceNumber)
      ? confidenceNumber <= 1
        ? Math.round(confidenceNumber * 100)
        : Math.round(confidenceNumber)
      : 0

    return {
      id: cleanText(id),
      text: cleanText(text),
      reasoning: cleanText(reasoning),
      warning: cleanText(warning),
      authorLine: cleanText(authorLine),
      doi: cleanText(claim?.doi || claim?.DOI || ''),
      status,
      confidence,
    }
  })
}

function extractScore(input, claims) {
  const possible =
    input?.credibilityScore ??
    input?.credibility_score ??
    input?.score ??
    input?.overallScore ??
    input?.overall_score ??
    input?.summary?.credibilityScore ??
    input?.summary?.credibility_score

  const numeric = Number(possible)
  if (Number.isFinite(numeric)) {
    return numeric <= 1 ? Math.round(numeric * 100) : Math.round(numeric)
  }

  if (!claims.length) return 0

  const points = claims.reduce((sum, claim) => {
    if (claim.status === 'supported') return sum + 1
    if (claim.status === 'partial' || claim.status === 'partially_supported') return sum + 0.5
    return sum
  }, 0)

  return Math.round((points / claims.length) * 100)
}

function reliabilityLabel(score) {
  if (score >= 85) return 'Reliable'
  if (score >= 60) return 'Partially Reliable'
  if (score >= 35) return 'Low Reliability'
  return 'Not Reliable'
}

function reliabilityExplanation(score) {
  if (score >= 85) return 'Most claims appear to be supported by their cited sources.'
  if (score >= 60) return 'Some claims are inaccurate or unsupported by their cited sources.'
  if (score >= 35) return 'Several claims are unsupported or require manual verification.'
  return 'Most claims require manual verification against the original sources.'
}

function countStatuses(claims) {
  return {
    supported: claims.filter(c => c.status === 'supported').length,
    partial: claims.filter(c => c.status === 'partial' || c.status === 'partially_supported').length,
    unsupported: claims.filter(c => c.status === 'unsupported').length,
    hallucinated: claims.filter(c => c.status === 'hallucinated').length,
    insufficient: claims.filter(c => c.status === 'insufficient' || c.status === 'insufficient_evidence').length,
  }
}

function prepareInput(args) {
  const first = args[0] || {}
  const second = args[1]

  if (Array.isArray(first)) {
    return {
      raw: { claims: first, fileName: second },
      fileName: cleanText(second || 'uploaded_document.pdf'),
    }
  }

  return {
    raw: first,
    fileName: fileNameFromInput(first, second),
  }
}

function addHeader(doc, pageW, margin, fileName) {
  setText(doc, 18, 'bold', INK)
  doc.text('verifAi', margin, 17)

  setText(doc, 9, 'normal', MUTED)
  doc.text(`Verification Report · ${fileName} · ${formatDate()}`, margin, 25, {
    maxWidth: pageW - margin * 2,
  })

  line(doc, margin, 31, pageW - margin)
}

function addFooter(doc, pageW, pageH, margin, pageNumber, totalPages) {
  line(doc, margin, pageH - 22, pageW - margin)

  setText(doc, 7.5, 'normal', MUTED)
  doc.text(
    'VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors and accuracy is not guaranteed to be 100% — please verify critical claims against the original sources.',
    margin,
    pageH - 15,
    { maxWidth: pageW - margin * 2 - 28 }
  )

  setText(doc, 8, 'normal', MUTED)
  doc.text(`Page ${pageNumber} / ${totalPages}`, pageW - margin, pageH - 9, {
    align: 'right',
  })
}

function ensureSpace(doc, y, needed, layout, fileName) {
  const { pageW, pageH, margin } = layout
  if (y + needed < pageH - 30) return y

  doc.addPage()
  addHeader(doc, pageW, margin, fileName)
  return 41
}

function writeWrapped(doc, text, x, y, width, lineHeight = 5) {
  const lines = doc.splitTextToSize(cleanText(text), width)
  doc.text(lines, x, y)
  return y + lines.length * lineHeight
}

function drawSummary(doc, y, counts, margin, contentW) {
  setText(doc, 14, 'bold', INK)
  doc.text('Fazit — Claims Summary', margin, y)
  y += 8

  setText(doc, 10, 'normal', INK)

  const leftX = margin
  const rightX = margin + contentW / 2 + 5
  const valueLeftX = margin + contentW / 2 - 8
  const valueRightX = margin + contentW - 2

  doc.text('Supported', leftX, y)
  doc.text(String(counts.supported), valueLeftX, y, { align: 'right' })

  doc.text('Partially supported', rightX, y)
  doc.text(String(counts.partial), valueRightX, y, { align: 'right' })

  y += 7
  doc.text('Unsupported', leftX, y)
  doc.text(String(counts.unsupported), valueLeftX, y, { align: 'right' })

  doc.text('Hallucinated', rightX, y)
  doc.text(String(counts.hallucinated), valueRightX, y, { align: 'right' })

  y += 7
  doc.text('Insufficient evidence', leftX, y)
  doc.text(String(counts.insufficient), valueLeftX, y, { align: 'right' })

  return y + 13
}

function estimateClaimHeight(doc, claim, contentW) {
  const textLines = doc.splitTextToSize(`"${claim.text}"${claim.authorLine ? ` (${claim.authorLine})` : ''}`, contentW)
  const reasoningLines = doc.splitTextToSize(`AI reasoning: ${claim.reasoning || 'No reasoning provided.'}`, contentW)
  const warningLines = claim.warning ? doc.splitTextToSize(claim.warning, contentW) : []
  return 14 + textLines.length * 5.1 + reasoningLines.length * 5.1 + warningLines.length * 5.1 + 12
}

function drawClaim(doc, y, claim, index, layout, fileName) {
  const { pageW, margin, contentW } = layout

  y = ensureSpace(doc, y, estimateClaimHeight(doc, claim, contentW), layout, fileName)

  setText(doc, 9, 'bold', INK)
  doc.text('CLAIM', margin, y)

  setText(doc, 9, 'bold', MUTED)
  doc.text(claim.id || `result_${index}`, margin + 18, y, { maxWidth: contentW - 75 })

  const label = displayStatus(claim.status)
  setText(doc, 9, 'bold', statusColor(claim.status))
  doc.text(label, pageW - margin, y, { align: 'right' })

  y += 8

  setText(doc, 10, 'normal', INK)
  const citation = claim.authorLine ? ` (${claim.authorLine})` : ''
  y = writeWrapped(doc, `"${claim.text}"${citation}`, margin, y, contentW, 5.1)
  y += 5

  setText(doc, 9, 'normal', INK)
  y = writeWrapped(doc, `AI reasoning: ${claim.reasoning || 'No reasoning provided.'}`, margin, y, contentW, 5.1)
  y += 4

  if (claim.warning) {
    setText(doc, 9, 'normal', INK)
    y = writeWrapped(doc, claim.warning, margin, y, contentW, 5.1)
    y += 3
  } else if (claim.status === 'insufficient' || claim.status === 'insufficient_evidence') {
    setText(doc, 9, 'normal', INK)
    doc.text('Human review recommended - this result may need manual verification.', margin, y)
    y += 7
  }

  if (claim.doi) {
    setText(doc, 8.5, 'normal', MUTED)
    y = writeWrapped(doc, `DOI: ${claim.doi}`, margin, y, contentW, 4.8)
    y += 2
  }

  setText(doc, 9, 'normal', INK)
  doc.text(`Confidence ${claim.confidence}`, margin, y)
  y += 11

  return y
}

function buildReport(...args) {
  const { raw, fileName } = prepareInput(args)
  const claims = extractClaims(raw)
  const score = extractScore(raw, claims)
  const counts = countStatuses(claims)

  const doc = new jsPDF('p', 'mm', 'a4')
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 16
  const contentW = pageW - margin * 2
  const layout = { pageW, pageH, margin, contentW }

  addHeader(doc, pageW, margin, fileName)

  let y = 43

  setText(doc, 13, 'bold', INK)
  doc.text(`Credibility Score: ${score}% — ${reliabilityLabel(score)}`, margin, y)
  y += 8

  setText(doc, 10, 'normal', INK)
  y = writeWrapped(doc, reliabilityExplanation(score), margin, y, contentW, 5)
  y += 10

  y = drawSummary(doc, y, counts, margin, contentW)

  setText(doc, 14, 'bold', INK)
  doc.text('Claims Overview', margin, y)
  y += 10

  if (!claims.length) {
    setText(doc, 10, 'normal', INK)
    doc.text('No claims were available for this report.', margin, y)
  } else {
    claims.forEach((claim, index) => {
      y = drawClaim(doc, y, claim, index + 1, layout, fileName)
    })
  }

  const totalPages = doc.internal.getNumberOfPages()
  for (let page = 1; page <= totalPages; page += 1) {
    doc.setPage(page)
    addFooter(doc, pageW, pageH, margin, page, totalPages)
  }

  const cleanName = fileName.replace(/\.pdf$/i, '').replace(/[^\w.-]+/g, '_')
  doc.save(`verifai_report_${cleanName}.pdf`)
  return doc
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


export function generateVerificationPdf(...args) {
  return buildReport(...args)
}

export function generateVerificationPDF(...args) {
  return buildReport(...args)
}

export default buildReport
