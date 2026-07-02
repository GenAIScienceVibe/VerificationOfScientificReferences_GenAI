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

function drawHeader(doc, layout, fileName, logoB64) {
  const { pageW, margin } = layout

  // Navy top bar
  doc.setFillColor(...COLORS.navy)
  doc.rect(0, 0, pageW, 31, 'F')

  // Logo image or fallback text
  if (logoB64) {
    doc.addImage(logoB64, 'PNG', margin, 3, 22, 22)
    font(doc, 11, 'bold', [255, 255, 255])
    doc.text('verifAi', margin + 26, 18)
  } else {
    font(doc, 11, 'bold', [255, 255, 255])
    doc.text('verifAi', margin, 18)
  }

  const headerText = `Verification Report · ${fileName} · ${formatDate()}`
  font(doc, 7, 'normal', [180, 195, 220])
  doc.text(doc.splitTextToSize(headerText, pageW - margin * 2 - 50).slice(0, 2), pageW - margin, 16, { align: 'right' })
}

function drawFooter(doc, layout, page, total) {
  const { pageW, pageH, margin } = layout

  line(doc, margin, pageH - 19, pageW - margin, [232, 235, 241], 0.28)

  font(doc, 6.7, 'normal', COLORS.muted)
  doc.text(
    'VerifAI uses AI-assisted analysis and automated source matching. Results may contain errors — verify critical claims against original sources.',
    margin,
    pageH - 11,
    { maxWidth: pageW - margin * 2 - 32 }
  )

  font(doc, 7.2, 'normal', COLORS.muted)
  doc.text(`Page ${page} / ${total}`, pageW - margin, pageH - 11, { align: 'right' })
}

function ensurePage(doc, y, needed, layout, fileName, logoB64) {
  if (y + needed <= layout.pageH - 24) return y

  doc.addPage()
  doc.setFillColor(...COLORS.softBg)
  doc.rect(0, 0, layout.pageW, layout.pageH, 'F')
  drawHeader(doc, layout, fileName, logoB64)
  return 38
}

function drawDonut(doc, cx, cy, radius, score) {
  const color = scoreColor(score)

  doc.setFillColor(255, 255, 255)
  doc.setDrawColor(226, 230, 236)
  doc.setLineWidth(0.7)
  doc.circle(cx, cy, radius + 5, 'FD')

  doc.setFillColor(250, 250, 252)
  doc.setDrawColor(...color)
  doc.setLineWidth(0.9)
  doc.circle(cx, cy, radius + 1.5, 'FD')

  font(doc, 13.5, 'bold', COLORS.ink)
  doc.text(`${score}%`, cx, cy + 1.8, { align: 'center' })
}

function drawScorePanel(doc, x, y, w, score) {
  roundedCard(doc, x, y, w, 62)

  font(doc, 7, 'bold', COLORS.navy)
  doc.text('CREDIBILITY SCORE', x + w / 2, y + 10, { align: 'center' })

  drawDonut(doc, x + w / 2, y + 30, 10.5, score)

  font(doc, 8.5, 'bold', scoreColor(score))
  doc.text(scoreLabel(score), x + w / 2, y + 49, { align: 'center' })

  font(doc, 6.7, 'normal', COLORS.muted)
  const desc = doc.splitTextToSize(scoreDescription(score), w - 14)
  doc.text(desc, x + w / 2, y + 55, { align: 'center' })
}

function drawSummaryPanel(doc, x, y, w, c) {
  const h = 76
  roundedCard(doc, x, y, w, h)

  font(doc, 8.8, 'bold', COLORS.ink)
  doc.text('Claims Summary', x + 8, y + 11)

  const rows = [
    ['Supported', c.supported, COLORS.green],
    ['Partially supported', c.partial, COLORS.orange],
    ['Unsupported', c.unsupported, COLORS.red],
    ['Hallucinated', c.hallucinated, COLORS.purple],
    ['Insufficient evidence', c.insufficient, COLORS.gray],
  ]

  rows.forEach((row, index) => {
    const yy = y + 22 + index * 8.4

    doc.setFillColor(...row[2])
    doc.circle(x + 9, yy - 1.7, 1.15, 'F')

    font(doc, 6.9, 'normal', COLORS.body)
    const labelLines = doc.splitTextToSize(row[0], w - 28)
    doc.text(labelLines.slice(0, 1), x + 13, yy)

    font(doc, 7.8, 'bold', COLORS.ink)
    doc.text(String(row[1]), x + w - 7, yy, { align: 'right' })
  })

  const total = Object.values(c).reduce((s, n) => s + n, 0)
  const barX = x + 8
  const barY = y + 66
  const barW = w - 16
  const barH = 2.5

  doc.setFillColor(226, 230, 236)
  doc.roundedRect(barX, barY, barW, barH, 1.2, 1.2, 'F')

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
  roundedCard(doc, x, y, w, 29)

  doc.setFillColor(238, 242, 255)
  doc.roundedRect(x + 8, y + 7, 12, 12, 2, 2, 'F')

  font(doc, 8.2, 'bold', COLORS.ink)
  const fileLines = doc.splitTextToSize(fileName, w - 32)
  doc.text(fileLines.slice(0, 2), x + 25, y + 11)

  font(doc, 7.1, 'normal', COLORS.muted)
  doc.text(`${claimsCount} claims processed`, x + 25, y + 23)
}

function drawClaimCard(doc, y, claim, index, layout, fileName, logoB64) {
  const { mainX, mainW } = layout
  const info = statusInfo(claim.status)

  const padX = 8
  const textW = mainW - padX * 2 - 4
  const citation = claim.citation ? ` ${claim.citation}` : ''

  // Important: set font BEFORE splitTextToSize, otherwise jsPDF calculates wrapping incorrectly.
  font(doc, 8.4, 'normal', COLORS.ink)
  const quoteLines = doc.splitTextToSize(`"${claim.text}"${citation}`, textW)

  font(doc, 7.6, 'italic', COLORS.body)
  const sourceLines = claim.sourceTitle ? doc.splitTextToSize(claim.sourceTitle, textW) : []

  font(doc, 7.0, 'normal', COLORS.muted)
  const authorLines = claim.authorLine ? doc.splitTextToSize(claim.authorLine, textW) : []

  font(doc, 7.7, 'normal', COLORS.body)
  const reasoningLines = doc.splitTextToSize(claim.reasoning || 'No reasoning provided.', textW - 10)

  const warning =
    claim.warning ||
    (claim.status === 'supported' ? '' : 'Human review recommended - this result may need manual verification.')

  font(doc, 7.4, 'normal', COLORS.body)
  const warningLines = warning ? doc.splitTextToSize(warning, textW) : []

  const h =
    30 +
    quoteLines.length * 5.2 +
    sourceLines.length * 4.6 +
    authorLines.length * 4.4 +
    15 +
    reasoningLines.length * 4.9 +
    warningLines.length * 4.8 +
    22

  y = ensurePage(doc, y, h, layout, fileName, logoB64)

  roundedCard(doc, mainX, y, mainW, h, COLORS.cardBg, COLORS.border)

  // Colored left accent bar
  doc.setFillColor(...info.color)
  doc.roundedRect(mainX, y, 4, h, 2, 2, 'F')
  doc.setFillColor(...info.color)
  doc.rect(mainX + 2, y, 2, h, 'F')

  font(doc, 7.1, 'bold', COLORS.muted)
  doc.text(`CLAIM ${index}`, mainX + padX, y + 12)

  const badgeW = Math.min(Math.max(30, doc.getTextWidth(info.label) + 11), 44)
  const badgeX = mainX + mainW - badgeW - 8
  const badgeY = y + 7
  const badgeH = 8.5

  doc.setFillColor(...info.pale)
  doc.setDrawColor(...info.color)
  doc.setLineWidth(0.32)
  doc.roundedRect(badgeX, badgeY, badgeW, badgeH, 4.2, 4.2, 'FD')

  font(doc, 6.9, 'bold', info.color)
  const badgeText = doc.splitTextToSize(info.label, badgeW - 5)
  doc.text(badgeText.slice(0, 1), badgeX + badgeW / 2, badgeY + 5.7, {
    align: 'center',
  })

  let yy = y + 24

  font(doc, 8.4, 'normal', COLORS.ink)
  doc.text(quoteLines, mainX + padX, yy)
  yy += quoteLines.length * 5.2 + 7

  if (sourceLines.length) {
    font(doc, 7.6, 'italic', COLORS.body)
    doc.text(sourceLines, mainX + padX, yy)
    yy += sourceLines.length * 4.6 + 2
  }

  if (authorLines.length) {
    font(doc, 7.0, 'normal', COLORS.muted)
    doc.text(authorLines, mainX + padX, yy)
    yy += authorLines.length * 4.4 + 4
  }

  if (claim.doi) {
    doc.setFillColor(245, 247, 250)
    doc.roundedRect(mainX + padX, yy - 4, 30, 6.5, 3, 3, 'F')
    font(doc, 6.7, 'normal', COLORS.body)
    doc.text('✓ DOI resolved', mainX + padX + 3, yy + 0.6)
    yy += 8
  }

  const reasoningH = 11 + reasoningLines.length * 4.9
  doc.setFillColor(...COLORS.reasoningBg)
  doc.roundedRect(mainX + padX, yy, textW, reasoningH, 2.4, 2.4, 'F')

  font(doc, 6.7, 'bold', COLORS.muted)
  doc.text('AI REASONING', mainX + padX + 4, yy + 6)

  font(doc, 7.7, 'normal', COLORS.body)
  doc.text(reasoningLines, mainX + padX + 4, yy + 13)
  yy += reasoningH + 7

  if (warningLines.length) {
    font(doc, 7.4, 'normal', COLORS.body)
    doc.text(warningLines, mainX + padX, yy)
    yy += warningLines.length * 4.8 + 6
  }

  font(doc, 7.3, 'normal', COLORS.muted)
  doc.text('Confidence', mainX + padX, yy + 1)

  const barX = mainX + padX + 25
  const barY = yy
  const barW = 40

  doc.setDrawColor(225, 229, 235)
  doc.setLineWidth(1.7)
  doc.line(barX, barY, barX + barW, barY)

  doc.setDrawColor(...info.color)
  doc.setLineWidth(1.7)
  doc.line(barX, barY, barX + (Math.max(0, Math.min(100, claim.confidence)) / 100) * barW, barY)

  font(doc, 7.1, 'normal', COLORS.muted)
  doc.text(`${claim.confidence}.0%`, barX + barW + 5, yy + 1)

  return y + h + 9
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

async function buildReport(...args) {
  const { raw, fileName } = inputFromArgs(args)
  const claims = getClaims(raw)
  const score = getScore(raw, claims)
  const c = countClaims(claims)

  const logoSrc = raw?.logo || null
  const logoB64 = logoSrc ? await loadImg(logoSrc) : null

  const doc = new jsPDF('p', 'mm', 'a4')
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 13

  const sidebarW = 54
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

  drawHeader(doc, layout, fileName, logoB64)

  drawScorePanel(doc, margin, 40, sidebarW, score)
  drawSummaryPanel(doc, margin, 105, sidebarW, c)
  drawDocumentPanel(doc, margin, 193, sidebarW, fileName, claims.length)

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
    font(doc, 6.7, 'bold', color)
    const w = doc.getTextWidth(text) + 10
    doc.setFillColor(...pale)
    doc.setDrawColor(...color)
    doc.setLineWidth(0.3)
    doc.roundedRect(chipX, 61, w, 8.3, 4.1, 4.1, 'FD')
    font(doc, 6.7, 'bold', color)
    doc.text(text, chipX + w / 2, 66.6, { align: 'center' })
    chipX += w + 3
  })

  let y = 80

  if (!claims.length) {
    roundedCard(doc, mainX, y, mainW, 28)
    font(doc, 8.5, 'normal', COLORS.muted)
    doc.text('No claims were available for this report.', mainX + 8, y + 15)
  } else {
    claims.forEach((claim, index) => {
      y = drawClaimCard(doc, y, claim, index + 1, layout, fileName, logoB64)
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
