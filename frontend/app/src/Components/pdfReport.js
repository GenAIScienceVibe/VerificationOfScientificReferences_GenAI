import jsPDF from 'jspdf'

const COLORS = {
  navy: [26, 58, 107],
  navyDark: [18, 43, 84],
  ink: [24, 27, 32],
  body: [68, 72, 80],
  muted: [137, 141, 150],
  border: [226, 230, 236],
  softBg: [248, 249, 251],
  cardBg: [255, 255, 255],
  reasoningBg: [248, 249, 251],
  green: [22, 163, 74],
  orange: [217, 119, 6],
  red: [239, 68, 68],
  purple: [126, 34, 206],
  gray: [107, 114, 128],
}

const STATUS = {
  supported: {
    label: 'Supported',
    color: COLORS.green,
    pale: [236, 253, 245],
  },
  partial: {
    label: 'Partially supported',
    color: COLORS.orange,
    pale: [255, 247, 237],
  },
  partially_supported: {
    label: 'Partially supported',
    color: COLORS.orange,
    pale: [255, 247, 237],
  },
  unsupported: {
    label: 'Unsupported',
    color: COLORS.red,
    pale: [254, 242, 242],
  },
  hallucinated: {
    label: 'Hallucinated',
    color: COLORS.purple,
    pale: [250, 245, 255],
  },
  insufficient: {
    label: 'Insufficient Evidence',
    color: COLORS.gray,
    pale: [248, 250, 252],
  },
  insufficient_evidence: {
    label: 'Insufficient Evidence',
    color: COLORS.gray,
    pale: [248, 250, 252],
  },
}

function font(doc, size, style = 'normal', color = COLORS.ink) {
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

function formatDate() {
  const d = new Date()
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
}

function toArray(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'object') return Object.values(value)
  return []
}

function writeWrapped(doc, text, x, y, width, lineHeight = 4.8) {
  const lines = doc.splitTextToSize(clean(text), width)
  doc.text(lines, x, y)
  return y + lines.length * lineHeight
}

function roundedCard(doc, x, y, w, h, fill = COLORS.cardBg, stroke = COLORS.border) {
  // subtle shadow, similar to the cards in the web UI
  doc.setFillColor(242, 244, 248)
  doc.roundedRect(x + 0.9, y + 1.1, w, h, 4.5, 4.5, 'F')

  doc.setFillColor(...fill)
  doc.setDrawColor(...stroke)
  doc.setLineWidth(0.32)
  doc.roundedRect(x, y, w, h, 4.5, 4.5, 'FD')
}

function line(doc, x1, y, x2, color = COLORS.border, width = 0.35) {
  doc.setDrawColor(...color)
  doc.setLineWidth(width)
  doc.line(x1, y, x2, y)
}

function parseClaimText(value) {
  let t = clean(value)

  t = t.replace(/^"+/, '"').replace(/"+$/, '"')

  let match = t.match(/^["“](.*?)["”]\s*(\([^)]+\))?$/)
  if (match) {
    return {
      statement: clean(match[1]),
      citation: clean(match[2] || ''),
    }
  }

  match = t.match(/^(.*?)\s+(\([^)]*\d{4}[^)]*\))$/)
  if (match) {
    return {
      statement: clean(match[1]).replace(/^["“]+|["”]+$/g, ''),
      citation: clean(match[2]),
    }
  }

  return {
    statement: t.replace(/^["“]+|["”]+$/g, ''),
    citation: '',
  }
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
    const parsed = parseClaimText(
      claim?.text ||
      claim?.claim ||
      claim?.claim_text ||
      claim?.statement ||
      claim?.content ||
      claim?.sentence ||
      ''
    )

    const rawConfidence =
      claim?.confidence ??
      claim?.confidence_score ??
      claim?.score ??
      0

    const n = Number(rawConfidence)
    const confidence = Number.isFinite(n)
      ? n <= 1
        ? Math.round(n * 100)
        : Math.round(n)
      : 0

    const authorLine = clean(
      claim?.authorLine ||
      claim?.author_line ||
      claim?.source ||
      claim?.reference ||
      ''
    )

    const sourceTitle = clean(
      claim?.sourceTitle ||
      claim?.source_title ||
      claim?.title ||
      claim?.paper_title ||
      claim?.reference_title ||
      ''
    )

    return {
      id: clean(
        claim?.id ||
        claim?.claim_id ||
        claim?.claimId ||
        claim?.result_id ||
        claim?.resultId ||
        `result_${String(index + 1).padStart(2, '0')}`
      ),
      text: parsed.statement,
      citation: parsed.citation,
      sourceTitle,
      authorLine,
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
  if (score >= 85) return 'High Reliability'
  if (score >= 60) return 'Partially Reliable'
  if (score >= 35) return 'Low Reliability'
  return 'Low Reliability'
}

function scoreColor(score) {
  if (score >= 85) return COLORS.green
  if (score >= 60) return COLORS.orange
  return COLORS.red
}

function scoreDescription(score) {
  if (score >= 85) return 'Most claims appear to be supported by their cited sources.'
  if (score >= 60) return 'Some claims are inaccurate or unsupported by their cited sources.'
  return 'A significant portion of claims could not be verified or are unsupported.'
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

function drawLogo(doc, x, y) {
  font(doc, 10, 'bold', COLORS.navy)
  doc.text('verif', x, y)

  const cx = x + 19
  const cy = y - 2.4

  doc.setDrawColor(48, 133, 214)
  doc.setLineWidth(0.45)
  for (let i = 0; i < 14; i += 1) {
    const a = (Math.PI * 2 * i) / 14
    doc.line(
      cx + Math.cos(a) * 1.7,
      cy + Math.sin(a) * 1.7,
      cx + Math.cos(a) * 4.2,
      cy + Math.sin(a) * 4.2
    )
  }
}

function drawHeader(doc, layout, fileName) {
  const { pageW, margin } = layout

  doc.setFillColor(255, 255, 255)
  doc.rect(0, 0, pageW, 30, 'F')

  drawLogo(doc, margin, 18)

  font(doc, 7.4, 'normal', COLORS.muted)
  doc.text(`Verification Report · ${fileName} · ${formatDate()}`, pageW - margin, 18, {
    align: 'right',
  })

  line(doc, margin, 29, pageW - margin, [232, 235, 241], 0.3)
}

function drawFooter(doc, layout, page, total) {
  const { pageW, pageH, margin } = layout

  line(doc, margin, pageH - 18, pageW - margin, [232, 235, 241], 0.3)

  font(doc, 6.8, 'normal', COLORS.muted)
  doc.text(
    'VerifAI uses AI-assisted analysis and automated source matching. Results may contain errors — verify critical claims against original sources.',
    margin,
    pageH - 10,
    { maxWidth: pageW - margin * 2 - 28 }
  )

  font(doc, 7.2, 'normal', COLORS.muted)
  doc.text(`Page ${page} / ${total}`, pageW - margin, pageH - 10, { align: 'right' })
}

function ensurePage(doc, y, needed, layout, fileName) {
  if (y + needed <= layout.pageH - 24) return y

  doc.addPage()
  drawHeader(doc, layout, fileName)
  return 38
}

function drawDonut(doc, cx, cy, radius, score) {
  const color = scoreColor(score)

  doc.setDrawColor(226, 226, 226)
  doc.setLineWidth(4)
  doc.circle(cx, cy, radius, 'S')

  const start = -90
  const end = start + (360 * Math.max(0, Math.min(score, 100))) / 100
  const steps = Math.max(8, Math.round((end - start) / 8))

  doc.setDrawColor(...color)
  doc.setLineWidth(4)

  let prev = null
  for (let i = 0; i <= steps; i += 1) {
    const angle = (Math.PI / 180) * (start + ((end - start) * i) / steps)
    const point = {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    }
    if (prev) doc.line(prev.x, prev.y, point.x, point.y)
    prev = point
  }

  font(doc, 12, 'bold', COLORS.ink)
  doc.text(`${score}%`, cx, cy + 1.5, { align: 'center' })
}

function drawScorePanel(doc, x, y, w, score) {
  roundedCard(doc, x, y, w, 58)

  font(doc, 7, 'bold', COLORS.navy)
  doc.text('CREDIBILITY SCORE', x + w / 2, y + 10, { align: 'center' })

  drawDonut(doc, x + w / 2, y + 29, 13, score)

  font(doc, 8.5, 'bold', scoreColor(score))
  doc.text(scoreLabel(score), x + w / 2, y + 47, { align: 'center' })

  font(doc, 6.8, 'normal', COLORS.muted)
  const desc = doc.splitTextToSize(scoreDescription(score), w - 12)
  doc.text(desc, x + w / 2, y + 53, { align: 'center' })
}

function drawSummaryPanel(doc, x, y, w, c) {
  const h = 61
  roundedCard(doc, x, y, w, h)

  font(doc, 8.5, 'bold', COLORS.ink)
  doc.text('Claims Summary', x + 8, y + 11)

  const rows = [
    ['Supported', c.supported, COLORS.green],
    ['Partially supported', c.partial, COLORS.orange],
    ['Unsupported', c.unsupported, COLORS.red],
    ['Hallucinated', c.hallucinated, COLORS.purple],
    ['Insufficient evidence', c.insufficient, COLORS.gray],
  ]

  rows.forEach((row, index) => {
    const yy = y + 20 + index * 7.2
    doc.setFillColor(...row[2])
    doc.circle(x + 9, yy - 1.7, 1.2, 'F')

    font(doc, 7.8, 'normal', COLORS.body)
    doc.text(row[0], x + 13, yy)

    font(doc, 7.8, 'bold', COLORS.ink)
    doc.text(String(row[1]), x + w - 8, yy, { align: 'right' })
  })

  const total = Object.values(c).reduce((s, n) => s + n, 0)
  const barX = x + 8
  const barY = y + 54
  const barW = w - 16
  const barH = 2.3

  doc.setFillColor(226, 230, 236)
  doc.roundedRect(barX, barY, barW, barH, 1.1, 1.1, 'F')

  let bx = barX
  rows.forEach(row => {
    const width = total ? (row[1] / total) * barW : 0
    if (width > 0) {
      doc.setFillColor(...row[2])
      doc.rect(bx, barY, width, barH, 'F')
      bx += width
    }
  })

  return h
}

function drawDocumentPanel(doc, x, y, w, fileName, claimsCount) {
  roundedCard(doc, x, y, w, 25)

  doc.setFillColor(238, 242, 255)
  doc.roundedRect(x + 8, y + 6, 12, 12, 2, 2, 'F')

  font(doc, 9, 'bold', COLORS.ink)
  doc.text(fileName, x + 25, y + 11)

  font(doc, 7.2, 'normal', COLORS.muted)
  doc.text(`${claimsCount} claims processed`, x + 25, y + 17)
}

function drawClaimCard(doc, y, claim, index, layout, fileName) {
  const { mainX, mainW, pageW, margin } = layout
  const info = statusInfo(claim.status)

  const textW = mainW - 16
  const citation = claim.citation ? ` ${claim.citation}` : ''
  const quoteLines = doc.splitTextToSize(`"${claim.text}"${citation}`, textW)
  const sourceLines = claim.sourceTitle ? doc.splitTextToSize(claim.sourceTitle, textW) : []
  const authorLines = claim.authorLine ? doc.splitTextToSize(claim.authorLine, textW) : []
  const reasoningLines = doc.splitTextToSize(claim.reasoning || 'No reasoning provided.', textW - 8)

  const warning =
    claim.warning ||
    (claim.status === 'supported' ? '' : 'Human review recommended - this result may need manual verification.')
  const warningLines = warning ? doc.splitTextToSize(warning, textW) : []

  const h =
    26 +
    quoteLines.length * 4.8 +
    sourceLines.length * 4.4 +
    authorLines.length * 4.2 +
    13 +
    reasoningLines.length * 4.6 +
    warningLines.length * 4.6 +
    18

  y = ensurePage(doc, y, h, layout, fileName)

  roundedCard(doc, mainX, y, mainW, h, COLORS.cardBg, info.color)

  font(doc, 7.2, 'bold', COLORS.muted)
  doc.text(`CLAIM ${index}`, mainX + 8, y + 12)

  const badgeW = Math.max(28, doc.getTextWidth(info.label) + 10)
  doc.setFillColor(...info.pale)
  doc.setDrawColor(...info.color)
  doc.setLineWidth(0.35)
  doc.roundedRect(mainX + mainW - badgeW - 7, y + 7, badgeW, 8, 4, 4, 'FD')

  font(doc, 7.5, 'bold', info.color)
  doc.text(info.label, mainX + mainW - badgeW / 2 - 7, y + 12.6, { align: 'center' })

  let yy = y + 22

  font(doc, 8.8, 'normal', COLORS.ink)
  doc.text(quoteLines, mainX + 8, yy)
  yy += quoteLines.length * 4.8 + 5

  if (sourceLines.length) {
    font(doc, 7.8, 'italic', COLORS.body)
    doc.text(sourceLines, mainX + 8, yy)
    yy += sourceLines.length * 4.4 + 2
  }

  if (authorLines.length) {
    font(doc, 7.2, 'normal', COLORS.muted)
    doc.text(authorLines, mainX + 8, yy)
    yy += authorLines.length * 4.2 + 3
  }

  if (claim.doi) {
    doc.setFillColor(245, 245, 245)
    doc.roundedRect(mainX + 8, yy - 3.8, 28, 6, 3, 3, 'F')
    font(doc, 6.7, 'normal', COLORS.body)
    doc.text('✓ DOI resolved', mainX + 11, yy + 0.5)
    yy += 7
  }

  doc.setFillColor(...COLORS.reasoningBg)
  doc.roundedRect(mainX + 8, yy, textW, 10 + reasoningLines.length * 4.6, 2, 2, 'F')

  font(doc, 6.8, 'bold', COLORS.muted)
  doc.text('AI REASONING', mainX + 12, yy + 6)

  font(doc, 7.9, 'normal', COLORS.body)
  doc.text(reasoningLines, mainX + 12, yy + 13)
  yy += 13 + reasoningLines.length * 4.6 + 6

  if (warningLines.length) {
    font(doc, 7.6, 'normal', COLORS.body)
    doc.text(warningLines, mainX + 8, yy)
    yy += warningLines.length * 4.6 + 5
  }

  font(doc, 7.4, 'normal', COLORS.muted)
  doc.text('Confidence', mainX + 8, yy + 1)

  const barX = mainX + 32
  const barY = yy
  const barW = 38

  doc.setDrawColor(225, 229, 235)
  doc.setLineWidth(1.8)
  doc.line(barX, barY, barX + barW, barY)

  doc.setDrawColor(...info.color)
  doc.setLineWidth(1.8)
  doc.line(barX, barY, barX + (Math.max(0, Math.min(100, claim.confidence)) / 100) * barW, barY)

  font(doc, 7.2, 'normal', COLORS.muted)
  doc.text(`${claim.confidence}.0%`, barX + barW + 5, yy + 1)

  return y + h + 7
}

function buildReport(...args) {
  const { raw, fileName } = inputFromArgs(args)
  const claims = getClaims(raw)
  const score = getScore(raw, claims)
  const c = countClaims(claims)

  const doc = new jsPDF('p', 'mm', 'a4')
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 13

  const sidebarW = 45
  const gap = 8
  const mainX = margin + sidebarW + gap
  const mainW = pageW - mainX - margin

  const layout = {
    pageW,
    pageH,
    margin,
    sidebarW,
    mainX,
    mainW,
    contentW: pageW - margin * 2,
  }

  doc.setFillColor(...COLORS.softBg)
  doc.rect(0, 0, pageW, pageH, 'F')

  drawHeader(doc, layout, fileName)

  drawScorePanel(doc, margin, 40, sidebarW, score)
  drawSummaryPanel(doc, margin, 105, sidebarW, c)
  drawDocumentPanel(doc, margin, 174, sidebarW, fileName, claims.length)

  font(doc, 17, 'bold', COLORS.ink)
  doc.text('Verification Results', mainX, 45)

  font(doc, 8.8, 'normal', COLORS.muted)
  doc.text(
    `${claims.length} claims checked · ${c.supported} supported · ${c.hallucinated + c.unsupported + c.insufficient} requiring review`,
    mainX,
    53
  )

  const chips = [
    ['All', claims.length, COLORS.navy, [236, 242, 255]],
    ['Supported', c.supported, COLORS.green, [236, 253, 245]],
    ['Partial', c.partial, COLORS.orange, [255, 247, 237]],
    ['Unsupported', c.unsupported, COLORS.red, [254, 242, 242]],
    ['Hallucinated', c.hallucinated, COLORS.purple, [250, 245, 255]],
  ]

  let chipX = mainX
  chips.forEach(([label, value, color, pale]) => {
    const text = `${label} ${value}`
    const w = doc.getTextWidth(text) + 9
    doc.setFillColor(...pale)
    doc.setDrawColor(...color)
    doc.setLineWidth(0.3)
    doc.roundedRect(chipX, 61, w, 8, 4, 4, 'FD')
    font(doc, 6.9, 'bold', color)
    doc.text(text, chipX + w / 2, 66.4, { align: 'center' })
    chipX += w + 3
  })

  let y = 78

  if (!claims.length) {
    roundedCard(doc, mainX, y, mainW, 28)
    font(doc, 8.5, 'normal', COLORS.muted)
    doc.text('No claims were available for this report.', mainX + 8, y + 15)
  } else {
    claims.forEach((claim, index) => {
      y = drawClaimCard(doc, y, claim, index + 1, layout, fileName)
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
