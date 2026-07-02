import jsPDF from 'jspdf'
import logoUrl from '../assets/Logo_VerifAi_pdf.png'

const COLORS = {
  navy: [26, 58, 107],
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

function loadImageDataUrl(url) {
  return new Promise(resolve => {
    if (!url || typeof window === 'undefined') return resolve(null)

    const img = new window.Image()
    img.crossOrigin = 'anonymous'

    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = img.naturalWidth || img.width
        canvas.height = img.naturalHeight || img.height
        canvas.getContext('2d').drawImage(img, 0, 0)
        resolve(canvas.toDataURL('image/png'))
      } catch {
        resolve(null)
      }
    }

    img.onerror = () => resolve(null)
    img.src = url
  })
}

function hexToRgb(hex, fallback = COLORS.orange) {
  if (!hex) return fallback
  const h = String(hex).replace('#', '').trim()
  if (h.length !== 6) return fallback
  const n = parseInt(h, 16)
  if (Number.isNaN(n)) return fallback
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
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

function roundedCard(doc, x, y, w, h, fill = COLORS.cardBg, stroke = COLORS.border) {
  doc.setFillColor(242, 244, 248)
  doc.roundedRect(x + 0.8, y + 1, w, h, 4.5, 4.5, 'F')

  doc.setFillColor(...fill)
  doc.setDrawColor(...stroke)
  doc.setLineWidth(0.32)
  doc.roundedRect(x, y, w, h, 4.5, 4.5, 'FD')
}

function line(doc, x1, y, x2, color = COLORS.border, width = 0.3) {
  doc.setDrawColor(...color)
  doc.setLineWidth(width)
  doc.line(x1, y, x2, y)
}

function formatDate() {
  const d = new Date()
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
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

function normalizeClaims(claims = []) {
  return (Array.isArray(claims) ? claims : []).map((claim, index) => {
    const parsed = parseClaimText(
      claim?.text ||
      claim?.claim ||
      claim?.claim_text ||
      claim?.statement ||
      claim?.content ||
      claim?.sentence ||
      ''
    )

    const rawConfidence = claim?.confidence ?? claim?.confidence_score ?? claim?.score ?? 0
    const n = Number(rawConfidence)
    const confidence = Number.isFinite(n)
      ? n <= 1
        ? Math.round(n * 100)
        : Math.round(n)
      : 0

    return {
      id: clean(claim?.id || claim?.claim_id || claim?.claimId || `result_${index + 1}`),
      text: parsed.statement,
      citation: parsed.citation,
      sourceTitle: clean(claim?.sourceTitle || claim?.source_title || claim?.title || claim?.paper_title || ''),
      authorLine: clean(claim?.authorLine || claim?.author_line || claim?.source || claim?.reference || ''),
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
      warning: clean(claim?.warning || claim?.human_review || claim?.review_note || claim?.note || ''),
      doi: clean(claim?.doi || claim?.DOI || ''),
      status: normalizeStatus(claim?.status || claim?.verification_status || claim?.result || claim?.label || claim?.category || ''),
      confidence,
    }
  })
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

function scoreColor(score, credibilityColor) {
  if (credibilityColor) return hexToRgb(credibilityColor)
  if (score >= 85) return COLORS.green
  if (score >= 60) return COLORS.orange
  return COLORS.red
}

function scoreLabel(score, provided) {
  if (provided) return provided
  if (score >= 85) return 'High Reliability'
  if (score >= 60) return 'Partially Reliable'
  return 'Low Reliability'
}

function scoreDescription(score) {
  if (score >= 85) return 'Most claims appear to be supported by their cited sources.'
  if (score >= 60) return 'Some claims are inaccurate or unsupported by their cited sources.'
  return 'A significant portion of claims could not be verified or are unsupported.'
}

function ensurePage(doc, y, needed, layout, fileName) {
  if (y + needed <= layout.pageH - 24) return y

  doc.addPage()
  drawHeader(doc, layout, fileName)
  return 38
}

function drawLogo(doc, x, y) {
  // Drawn logo instead of image asset, because PNG has transparent padding in PDF export.
  font(doc, 9.8, 'bold', COLORS.navy)
  doc.text('verif', x, y)

  const spinnerX = x + 18.5
  const spinnerY = y - 2.4
  const innerR = 1.8
  const outerR = 5.2

  doc.setDrawColor(37, 137, 255)
  doc.setLineWidth(0.45)

  for (let i = 0; i < 16; i += 1) {
    const a = (Math.PI * 2 * i) / 16
    const x1 = spinnerX + Math.cos(a) * innerR
    const y1 = spinnerY + Math.sin(a) * innerR
    const x2 = spinnerX + Math.cos(a) * outerR
    const y2 = spinnerY + Math.sin(a) * outerR
    doc.line(x1, y1, x2, y2)
  }

  font(doc, 9.8, 'bold', COLORS.navy)
  doc.text('Ai', x + 25, y)
}

function drawHeader(doc, layout, fileName) {
  const { pageW, margin } = layout

  doc.setFillColor(255, 255, 255)
  doc.rect(0, 0, pageW, 31, 'F')

  drawLogo(doc, margin, 18)

  const headerText = `Verification Report · ${fileName} · ${formatDate()}`
  const headerMaxW = pageW - margin * 2 - 58

  font(doc, 7.1, 'normal', COLORS.muted)
  const headerLines = doc.splitTextToSize(headerText, headerMaxW)

  doc.text(headerLines.slice(0, 2), pageW - margin, 16, {
    align: 'right',
  })

  line(doc, margin, 29, pageW - margin, [232, 235, 241], 0.3)
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

function drawScoreRing(doc, cx, cy, radius, score, color) {
  const safeScore = Math.max(0, Math.min(100, Number(score) || 0))

  doc.setDrawColor(226, 226, 226)
  doc.setLineWidth(4.2)
  doc.circle(cx, cy, radius, 'S')

  if (safeScore > 0) {
    const start = -90
    const end = start + (360 * safeScore) / 100
    const steps = Math.max(16, Math.round((end - start) / 4))

    doc.setDrawColor(...color)
    doc.setLineWidth(4.2)

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

    const startAngle = (Math.PI / 180) * start
    const endAngle = (Math.PI / 180) * end

    doc.setFillColor(...color)
    doc.circle(cx + Math.cos(startAngle) * radius, cy + Math.sin(startAngle) * radius, 2.1, 'F')
    doc.circle(cx + Math.cos(endAngle) * radius, cy + Math.sin(endAngle) * radius, 2.1, 'F')
  }

  font(doc, 12.8, 'bold', COLORS.ink)
  doc.text(`${safeScore.toFixed(1)}%`, cx, cy + 1.8, { align: 'center' })
}

function drawScorePanel(doc, x, y, w, score, label, color) {
  roundedCard(doc, x, y, w, 62)

  font(doc, 7, 'bold', COLORS.navy)
  doc.text('CREDIBILITY SCORE', x + w / 2, y + 10, { align: 'center' })

  drawScoreRing(doc, x + w / 2, y + 30, 13, score, color)

  font(doc, 8.5, 'bold', color)
  doc.text(label, x + w / 2, y + 50, { align: 'center' })

  font(doc, 6.7, 'normal', COLORS.muted)
  const desc = doc.splitTextToSize(scoreDescription(score), w - 14)
  doc.text(desc, x + w / 2, y + 56, { align: 'center' })
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
    doc.text(row[0], x + 13, yy, { maxWidth: w - 28 })

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
}

function drawDocumentPanel(doc, x, y, w, fileName, claimsCount) {
  roundedCard(doc, x, y, w, 29)

  // Smaller document icon box
  const iconX = x + 8
  const iconY = y + 8
  const iconSize = 10

  doc.setFillColor(238, 242, 255)
  doc.roundedRect(iconX, iconY, iconSize, iconSize, 2, 2, 'F')

  font(doc, 7.5, 'normal', COLORS.muted)
  doc.text('📄', iconX + iconSize / 2, iconY + 6.8, {
    align: 'center',
  })

  // Clean filename so it does not break weirdly
  const maxName = fileName.length > 32 ? `${fileName.slice(0, 29)}...` : fileName

  font(doc, 7.6, 'bold', COLORS.ink)
  const fileLines = doc.splitTextToSize(maxName, w - 28)
  doc.text(fileLines.slice(0, 2), x + 23, y + 11)

  font(doc, 7.1, 'normal', COLORS.muted)
  doc.text(`${claimsCount} claims processed`, x + 23, y + 23)
}

function drawChip(doc, x, y, label, value, color, pale) {
  const text = `${label} ${value}`
  font(doc, 6.8, 'bold', color)

  const h = 8.8
  const w = Math.max(20, doc.getTextWidth(text) + 11)

  doc.setFillColor(...pale)
  doc.setDrawColor(...color)
  doc.setLineWidth(0.35)
  doc.roundedRect(x, y, w, h, h / 2, h / 2, 'FD')

  font(doc, 6.8, 'bold', color)
  doc.text(text, x + w / 2, y + h / 2 + 0.45, {
    align: 'center',
    baseline: 'middle',
  })

  return w
}

function drawChips(doc, mainX, mainW, y, counts, totalClaims) {
  const chips = [
    ['All', totalClaims, COLORS.navy, [236, 242, 255]],
    ['Supported', counts.supported, COLORS.green, [236, 253, 245]],
    ['Partial', counts.partial, COLORS.orange, [255, 247, 237]],
    ['Unsupported', counts.unsupported, COLORS.red, [254, 242, 242]],
    ['Hallucinated', counts.hallucinated, COLORS.purple, [250, 245, 255]],
    ['Insufficient Evidence', counts.insufficient, COLORS.gray, [248, 250, 252]],
  ]

  let chipX = mainX
  let chipY = y

  chips.forEach(([label, value, color, pale]) => {
    font(doc, 6.6, 'bold', color)
    const neededW = doc.getTextWidth(`${label} ${value}`) + 10

    if (chipX + neededW > mainX + mainW) {
      chipX = mainX
      chipY += 10
    }

    const usedW = drawChip(doc, chipX, chipY, label, value, color, pale)
    chipX += usedW + 3
  })

  return chipY + 12
}

function drawClaimCard(doc, y, claim, index, layout, fileName) {
  const pageInfo = doc.internal.getCurrentPageInfo()
  const currentPage = pageInfo?.pageNumber || 1
  const info = statusInfo(claim.status)

  // Page 1 keeps the two-column layout. From page 2 onward, cards use the full page width and are centered.
  const cardX = currentPage === 1 ? layout.mainX : layout.margin + 16
  const cardW = currentPage === 1 ? layout.mainW : layout.pageW - layout.margin * 2 - 32

  const padX = 8
  const textW = cardW - padX * 2 - 8
  const citation = claim.citation ? ` ${claim.citation}` : ''

  // Set font before wrapping — otherwise jsPDF calculates line breaks badly.
  font(doc, 7.8, 'normal', COLORS.ink)
  const quoteLines = doc.splitTextToSize(`"${claim.text}"${citation}`, textW)

  font(doc, 7.1, 'italic', COLORS.body)
  const sourceLines = claim.sourceTitle ? doc.splitTextToSize(claim.sourceTitle, textW) : []

  font(doc, 6.5, 'normal', COLORS.muted)
  const authorLines = claim.authorLine ? doc.splitTextToSize(claim.authorLine, textW) : []

  font(doc, 7.2, 'normal', COLORS.body)
  const reasoningLines = doc.splitTextToSize(claim.reasoning || 'No reasoning provided.', textW - 10)

  const warning =
    claim.warning ||
    (claim.status === 'supported' ? '' : 'Human review recommended - this result may need manual verification.')

  font(doc, 6.9, 'normal', COLORS.body)
  const warningLines = warning ? doc.splitTextToSize(warning, textW) : []

  // More compact height, especially useful on pages 2+
  const h =
    27 +
    quoteLines.length * 4.7 +
    sourceLines.length * 4.1 +
    authorLines.length * 3.9 +
    12 +
    reasoningLines.length * 4.4 +
    warningLines.length * 4.2 +
    18

  y = ensurePage(doc, y, h, layout, fileName)

  // Recalculate after page break, because ensurePage may have moved us to a new page.
  const afterPageInfo = doc.internal.getCurrentPageInfo()
  const afterPage = afterPageInfo?.pageNumber || 1
  const finalCardX = afterPage === 1 ? layout.mainX : layout.margin + 16
  const finalCardW = afterPage === 1 ? layout.mainW : layout.pageW - layout.margin * 2 - 32
  const finalTextW = finalCardW - padX * 2 - 8

  roundedCard(doc, finalCardX, y, finalCardW, h, COLORS.cardBg, info.color)

  font(doc, 6.9, 'bold', COLORS.muted)
  doc.text(`CLAIM ${index}`, finalCardX + padX, y + 11)

  font(doc, 6.6, 'bold', info.color)
  const badgeW = Math.min(Math.max(34, doc.getTextWidth(info.label) + 12), 58)
  const badgeX = finalCardX + finalCardW - badgeW - 8
  const badgeY = y + 7
  const badgeH = 8.3

  doc.setFillColor(...info.pale)
  doc.setDrawColor(...info.color)
  doc.setLineWidth(0.32)
  doc.roundedRect(badgeX, badgeY, badgeW, badgeH, 4.1, 4.1, 'FD')

  const badgeText = doc.splitTextToSize(info.label, badgeW - 6)
  doc.text(badgeText.slice(0, 1), badgeX + badgeW / 2, badgeY + badgeH / 2 + 0.35, { align: 'center', baseline: 'middle' })

  let yy = y + 23

  font(doc, 7.8, 'normal', COLORS.ink)
  const safeQuoteLines = doc.splitTextToSize(`"${claim.text}"${citation}`, finalTextW)
  doc.text(safeQuoteLines, finalCardX + padX, yy)
  yy += safeQuoteLines.length * 4.7 + 6

  if (sourceLines.length) {
    font(doc, 7.1, 'italic', COLORS.body)
    const safeSourceLines = claim.sourceTitle ? doc.splitTextToSize(claim.sourceTitle, finalTextW) : []
    doc.text(safeSourceLines, finalCardX + padX, yy)
    yy += safeSourceLines.length * 4.1 + 2
  }

  if (authorLines.length) {
    font(doc, 6.5, 'normal', COLORS.muted)
    const safeAuthorLines = claim.authorLine ? doc.splitTextToSize(claim.authorLine, finalTextW) : []
    doc.text(safeAuthorLines, finalCardX + padX, yy)
    yy += safeAuthorLines.length * 3.9 + 4
  }

  if (claim.doi) {
    doc.setFillColor(245, 247, 250)
    doc.roundedRect(finalCardX + padX, yy - 4, 30, 6.2, 3, 3, 'F')
    font(doc, 6.4, 'normal', COLORS.body)
    doc.text('✓ DOI resolved', finalCardX + padX + 3, yy + 0.4)
    yy += 7
  }

  font(doc, 7.2, 'normal', COLORS.body)
  const safeReasoningLines = doc.splitTextToSize(claim.reasoning || 'No reasoning provided.', finalTextW - 10)
  const reasoningH = 10 + safeReasoningLines.length * 4.4

  doc.setFillColor(...COLORS.reasoningBg)
  doc.roundedRect(finalCardX + padX, yy, finalTextW, reasoningH, 2.4, 2.4, 'F')

  font(doc, 6.4, 'bold', COLORS.muted)
  doc.text('AI REASONING', finalCardX + padX + 4, yy + 5.7)

  font(doc, 7.2, 'normal', COLORS.body)
  doc.text(safeReasoningLines, finalCardX + padX + 4, yy + 12)
  yy += reasoningH + 6

  if (warningLines.length) {
    font(doc, 6.9, 'normal', COLORS.body)
    const safeWarningLines = warning ? doc.splitTextToSize(warning, finalTextW) : []
    doc.text(safeWarningLines, finalCardX + padX, yy)
    yy += safeWarningLines.length * 4.2 + 5
  }

  font(doc, 6.9, 'normal', COLORS.muted)
  doc.text('Confidence', finalCardX + padX, yy + 1)

  const barX = finalCardX + padX + 25
  const barY = yy
  const barW = 40

  doc.setDrawColor(225, 229, 235)
  doc.setLineWidth(1.6)
  doc.line(barX, barY, barX + barW, barY)

  doc.setDrawColor(...info.color)
  doc.setLineWidth(1.6)
  doc.line(barX, barY, barX + (Math.max(0, Math.min(100, claim.confidence)) / 100) * barW, barY)

  font(doc, 6.8, 'normal', COLORS.muted)
  doc.text(`${claim.confidence}.0%`, barX + barW + 5, yy + 1)

  return y + h + 8
}

async function buildReport({
  claims = [],
  fileName = 'uploaded_document.pdf',
  logo = null,
  credibilityScore = 0,
  credibilityLabel = '',
  credibilityColor = '',
} = {}) {
  const normalizedClaims = normalizeClaims(claims)
  const counts = countClaims(normalizedClaims)
  const score = Number(credibilityScore) || 0
  const scoreRgb = scoreColor(score, credibilityColor)
  const scoreText = scoreLabel(score, credibilityLabel)

  const logoData = await loadImageDataUrl(logo || logoUrl)

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
    logoData,
  }

  doc.setFillColor(...COLORS.softBg)
  doc.rect(0, 0, pageW, pageH, 'F')

  drawHeader(doc, layout, fileName)

  drawScorePanel(doc, margin, 40, sidebarW, score, scoreText, scoreRgb)
  drawSummaryPanel(doc, margin, 107, sidebarW, counts)
  drawDocumentPanel(doc, margin, 193, sidebarW, fileName, normalizedClaims.length)

  font(doc, 17, 'bold', COLORS.ink)
  doc.text('Verification Results', mainX, 45)

  const unresolvableCount = counts.hallucinated + counts.insufficient
  const resolvedDoiCount = Math.max(0, normalizedClaims.length - unresolvableCount)

  font(doc, 8.8, 'normal', COLORS.muted)
  doc.text(
    `${normalizedClaims.length} claims checked · ${resolvedDoiCount} DOIs resolved · ${unresolvableCount} unresolvable`,
    mainX,
    53
  )

  const yAfterChips = drawChips(doc, mainX, mainW, 61, counts, normalizedClaims.length)
  let y = yAfterChips + 6

  if (!normalizedClaims.length) {
    roundedCard(doc, mainX, y, mainW, 28)
    font(doc, 8.5, 'normal', COLORS.muted)
    doc.text('No claims were available for this report.', mainX + 8, y + 15)
  } else {
    normalizedClaims.forEach((claim, index) => {
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

export async function generateVerificationPdf(...args) {
  return buildReport(...args)
}

export async function generateVerificationPDF(...args) {
  return buildReport(...args)
}

export async function generatePdfReport(...args) {
  return buildReport(...args)
}

export async function generatePDFReport(...args) {
  return buildReport(...args)
}

export async function generateReport(...args) {
  return buildReport(...args)
}

export async function downloadPdfReport(...args) {
  return buildReport(...args)
}

export async function downloadPDFReport(...args) {
  return buildReport(...args)
}

export async function createPdfReport(...args) {
  return buildReport(...args)
}

export default buildReport
