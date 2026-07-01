import jsPDF from 'jspdf'

const NAVY = [26, 58, 107]
const LIGHT_GREY = [245, 246, 248]
const MID_GREY = [140, 140, 148]
const DARK = [30, 30, 35]

const hexToRgb = (hex) => {
  const clean = (hex || '#888888').replace('#', '')
  const bigint = parseInt(clean, 16)
  return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255]
}

const loadImageAsBase64 = (url) =>
  new Promise((resolve) => {
    const img = new window.Image()
    img.crossOrigin = 'Anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      canvas.getContext('2d').drawImage(img, 0, 0)
      resolve(canvas.toDataURL('image/png'))
    }
    img.onerror = () => resolve(null)
    img.src = url
  })

const getConfidenceColor = (c) => {
  if (c > 0.7) return '#16a34a'
  if (c > 0.4) return '#d97706'
  return '#dc2626'
}

// ─── helpers ────────────────────────────────────────────────────────────────

function setFont(doc, size, style = 'normal', color = DARK) {
  doc.setFont(undefined, style)
  doc.setFontSize(size)
  doc.setTextColor(...color)
}

function drawRoundRect(doc, x, y, w, h, r, fillColor, strokeColor) {
  if (fillColor) doc.setFillColor(...fillColor)
  if (strokeColor) doc.setDrawColor(...strokeColor)
  else doc.setDrawColor(220, 222, 228)
  doc.setLineWidth(0.3)
  doc.roundedRect(x, y, w, h, r, r, fillColor ? (strokeColor !== false ? 'FD' : 'F') : 'D')
}

// ─── page chrome ─────────────────────────────────────────────────────────────

function drawHeader(doc, { pageWidth, margin, logoBase64, fileName }) {
  doc.setFillColor(255, 255, 255)
  doc.rect(0, 0, pageWidth, 28, 'F')

  if (logoBase64) doc.addImage(logoBase64, 'PNG', margin, 5, 16, 16)

  const tx = logoBase64 ? margin + 20 : margin
  setFont(doc, 13, 'bold', NAVY)
  doc.text('verifAi', tx, 14)
  setFont(doc, 7.5, 'normal', MID_GREY)
  doc.text(`Verification Report  ·  ${fileName}  ·  ${new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}`, tx, 21)

  doc.setDrawColor(220, 222, 228)
  doc.setLineWidth(0.3)
  doc.line(margin, 28, pageWidth - margin, 28)
}

function drawFooter(doc, { pageWidth, pageHeight, margin, contentWidth, pageNum, totalPages }) {
  doc.setDrawColor(220, 222, 228)
  doc.setLineWidth(0.3)
  doc.line(margin, pageHeight - 18, pageWidth - margin, pageHeight - 18)

  setFont(doc, 7, 'italic', MID_GREY)
  const disclaimer = doc.splitTextToSize(
    'VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors — please verify critical claims against the original sources.',
    contentWidth - 30
  )
  doc.text(disclaimer, margin, pageHeight - 12)

  setFont(doc, 7.5, 'normal', MID_GREY)
  doc.text(`${pageNum} / ${totalPages}`, pageWidth - margin, pageHeight - 12, { align: 'right' })
}

// ─── cover page ──────────────────────────────────────────────────────────────

function drawCoverPage(doc, { pageWidth, pageHeight, margin, contentWidth, logoBase64, fileName, credibilityScore, credibilityLabel, credibilityColor, summaryItems }) {
  // Dark navy header band
  doc.setFillColor(...NAVY)
  doc.rect(0, 0, pageWidth, 72, 'F')

  if (logoBase64) doc.addImage(logoBase64, 'PNG', margin, 12, 22, 22)

  setFont(doc, 22, 'bold', [255, 255, 255])
  doc.text('verifAi', margin + (logoBase64 ? 27 : 0), 24)
  setFont(doc, 9, 'normal', [180, 200, 230])
  doc.text('AI-Powered Citation Verification', margin + (logoBase64 ? 27 : 0), 32)

  setFont(doc, 14, 'bold', [255, 255, 255])
  doc.text('Verification Report', margin, 52)
  setFont(doc, 8.5, 'normal', [180, 200, 230])
  const shortName = fileName.length > 60 ? fileName.slice(0, 57) + '...' : fileName
  doc.text(shortName, margin, 62)

  // Credibility score card
  let y = 90
  drawRoundRect(doc, margin, y, contentWidth, 48, 4, [255, 255, 255], null)

  const [cr, cg, cb] = hexToRgb(credibilityColor)
  const scoreText = `${credibilityScore.toFixed(1)}%`

  setFont(doc, 8, 'bold', MID_GREY)
  doc.text('CREDIBILITY SCORE', margin + 10, y + 12)

  setFont(doc, 28, 'bold', [cr, cg, cb])
  doc.text(scoreText, margin + 10, y + 33)

  setFont(doc, 10, 'bold', [cr, cg, cb])
  doc.text(credibilityLabel, margin + 10, y + 42)

  // Mini bar chart
  const barX = margin + contentWidth / 2
  const barW = contentWidth / 2 - 16
  const total = summaryItems.reduce((s, i) => s + i.count, 0)
  let bx = barX
  doc.setFillColor(230, 232, 236)
  doc.roundedRect(barX, y + 22, barW, 5, 2, 2, 'F')
  summaryItems.forEach(item => {
    const segW = total > 0 ? (item.count / total) * barW : 0
    if (segW > 0) {
      const [r, g, b] = hexToRgb(item.color)
      doc.setFillColor(r, g, b)
      doc.rect(bx, y + 22, segW, 5, 'F')
      bx += segW
    }
  })

  let legendY = y + 32
  summaryItems.forEach((item, i) => {
    const lx = barX + (i % 2) * (barW / 2)
    const ly = legendY + Math.floor(i / 2) * 7
    const [r, g, b] = hexToRgb(item.color)
    doc.setFillColor(r, g, b)
    doc.circle(lx + 2, ly - 1.5, 1.5, 'F')
    setFont(doc, 7.5, 'normal', [80, 80, 80])
    doc.text(`${item.label}  ${item.count}`, lx + 6, ly)
  })

  y += 64

  // Summary stats row
  const statsY = y
  const cols = [
    { label: 'Total Claims', value: total },
    { label: 'DOIs Resolved', value: summaryItems[0]?.doiResolved ?? '—' },
    { label: 'Generated', value: new Date().toLocaleDateString('en-GB') },
  ]
  const colW = contentWidth / cols.length
  cols.forEach((col, i) => {
    const cx = margin + i * colW
    drawRoundRect(doc, cx + 2, statsY, colW - 4, 26, 3, LIGHT_GREY, false)
    setFont(doc, 14, 'bold', NAVY)
    doc.text(String(col.value), cx + 8, statsY + 13)
    setFont(doc, 7.5, 'normal', MID_GREY)
    doc.text(col.label, cx + 8, statsY + 21)
  })

  y = statsY + 36

  // Methodology box
  drawRoundRect(doc, margin, y, contentWidth, 52, 3, LIGHT_GREY, false)
  setFont(doc, 9, 'bold', NAVY)
  doc.text('Methodology', margin + 8, y + 10)
  setFont(doc, 8, 'normal', [60, 60, 60])
  const steps = [
    '1.  PDF uploaded and text extracted from the research paper.',
    '2.  Citations and references identified and DOIs resolved via CrossRef / OpenAlex.',
    '3.  Claims linked to citations are extracted using the Llama 4 language model.',
    '4.  Source documents retrieved and compared semantically via RAG pipeline.',
    '5.  Each claim is verified and assigned a verdict with a confidence score.',
  ]
  steps.forEach((step, i) => {
    doc.text(step, margin + 8, y + 20 + i * 7)
  })

  y += 62

  // Disclaimer
  drawRoundRect(doc, margin, y, contentWidth, 22, 3, [255, 248, 230], [253, 186, 116])
  setFont(doc, 7.5, 'italic', [120, 80, 20])
  const disc = doc.splitTextToSize(
    'Disclaimer: VerifAi uses AI-assisted analysis. Results may contain errors. Always verify critical claims against original sources before drawing conclusions.',
    contentWidth - 16
  )
  doc.text(disc, margin + 8, y + 8)
}

// ─── section divider ─────────────────────────────────────────────────────────

function drawSectionDivider(doc, { margin, contentWidth, y, title }) {
  doc.setFillColor(...NAVY)
  doc.rect(margin, y, contentWidth, 10, 'F')
  setFont(doc, 8.5, 'bold', [255, 255, 255])
  doc.text(title, margin + 6, y + 7)
  return y + 16
}

// ─── category reference page ──────────────────────────────────────────────────

function drawCategoryPage(doc, { pageWidth, pageHeight, margin, contentWidth, logoBase64, fileName }) {
  doc.addPage()
  drawHeader(doc, { pageWidth, margin, logoBase64, fileName })
  let y = 38

  y = drawSectionDivider(doc, { margin, contentWidth, y, title: 'Verdict Category Reference' })

  const categories = [
    {
      key: 'Supported',
      color: '#16a34a',
      bg: '#dcfce7',
      desc: 'The cited source explicitly confirms the claim. The AI found matching evidence and the source text directly supports the stated fact.',
      note: 'Strongest indicator of citation accuracy.',
    },
    {
      key: 'Partially Supported',
      color: '#d97706',
      bg: '#fef3c7',
      desc: 'The source partially supports the claim. Some aspects match but not all details are confirmed — figures or timeframes may differ.',
      note: 'Review the specific discrepancy noted in AI reasoning.',
    },
    {
      key: 'Unsupported',
      color: '#dc2626',
      bg: '#fee2e2',
      desc: 'The source was found but does not support the claim. The content contradicts or omits the stated fact.',
      note: 'Recommend revising or removing the claim.',
    },
    {
      key: 'Hallucinated',
      color: '#7c3aed',
      bg: '#f3e8ff',
      desc: 'The cited source could not be verified — the DOI is invalid, the reference does not appear to exist, or the source was fabricated.',
      note: 'Strongest signal of a fabricated citation.',
    },
    {
      key: 'Insufficient Evidence',
      color: '#6b7280',
      bg: '#f3f4f6',
      desc: 'The system could not retrieve enough text from the cited source. This may be due to a paywall, limited open-access availability, or low similarity scores.',
      note: 'Upload the source PDF manually on the results page to enable full re-verification.',
    },
  ]

  categories.forEach(cat => {
    const [cr, cg, cb] = hexToRgb(cat.color)
    const [bgr, bgg, bgb] = hexToRgb(cat.bg)
    const descLines = doc.splitTextToSize(cat.desc, contentWidth - 24)
    const noteLines = doc.splitTextToSize(cat.note, contentWidth - 24)
    const cardH = 14 + descLines.length * 5 + noteLines.length * 5 + 10

    drawRoundRect(doc, margin, y, contentWidth, cardH, 3, [255, 255, 255], null)
    doc.setFillColor(cr, cg, cb)
    doc.roundedRect(margin, y, 4, cardH, 1.5, 1.5, 'F')

    setFont(doc, 9, 'bold', [cr, cg, cb])
    doc.text(cat.key, margin + 10, y + 9)

    setFont(doc, 8.5, 'normal', [50, 50, 50])
    doc.text(descLines, margin + 10, y + 16)

    setFont(doc, 8, 'italic', [cr, cg, cb])
    doc.text(noteLines, margin + 10, y + 16 + descLines.length * 5 + 3)

    y += cardH + 6
    if (y > pageHeight - 30) {
      doc.addPage()
      drawHeader(doc, { pageWidth, margin, logoBase64, fileName })
      y = 38
    }
  })

  return y
}

// ─── claim card ───────────────────────────────────────────────────────────────

function drawClaimCard(doc, { claim, config, margin, contentWidth, pageWidth, pageHeight, y, headerCtx, checkPageBreak }) {
  const [cr, cg, cb] = hexToRgb(config.color)
  const [bgr, bgg, bgb] = hexToRgb(config.bg)

  const textLines = doc.splitTextToSize(`"${claim.text}"`, contentWidth - 22)
  const reasoningLines = doc.splitTextToSize(claim.reasoning || '', contentWidth - 22)
  const warningLines = claim.warning ? doc.splitTextToSize(claim.warning, contentWidth - 22) : []
  const authorLine = claim.authorLine || ''
  const doi = claim.doi || ''

  let blockH = 10 + textLines.length * 5 + 6 + reasoningLines.length * 5 + 6 + 10
  if (warningLines.length) blockH += warningLines.length * 5 + 5
  if (authorLine) blockH += 7
  if (doi) blockH += 6

  checkPageBreak(blockH)

  const sy = y

  // card background
  doc.setFillColor(255, 255, 255)
  doc.setDrawColor(bgr, bgg, bgb)
  doc.setLineWidth(0.4)
  doc.roundedRect(margin, sy, contentWidth, blockH, 3, 3, 'FD')

  // left accent bar
  doc.setFillColor(cr, cg, cb)
  doc.roundedRect(margin, sy, 3.5, blockH, 1.5, 1.5, 'F')

  let iy = sy + 8

  // claim id + badge
  setFont(doc, 8, 'bold', MID_GREY)
  doc.text(`CLAIM ${claim.displayId}`, margin + 9, iy)

  const badgeText = config.label
  const bw = doc.getTextWidth(badgeText) + 8
  const bx = pageWidth - margin - bw - 4
  doc.setFillColor(bgr, bgg, bgb)
  doc.roundedRect(bx, iy - 5, bw, 6.5, 2, 2, 'F')
  setFont(doc, 7.5, 'bold', [cr, cg, cb])
  doc.text(badgeText, bx + 4, iy)
  iy += 7

  // claim text
  setFont(doc, 9, 'italic', [40, 40, 40])
  doc.text(textLines, margin + 9, iy)
  iy += textLines.length * 5 + 4

  // author + doi
  if (authorLine) {
    setFont(doc, 7.5, 'normal', MID_GREY)
    doc.text(`Source: ${authorLine}`, margin + 9, iy)
    iy += 6
  }
  if (doi) {
    setFont(doc, 7.5, 'normal', [37, 99, 235])
    doc.text(`DOI: ${doi}`, margin + 9, iy)
    iy += 6
  }

  // reasoning
  setFont(doc, 8, 'normal', [70, 70, 70])
  doc.setFillColor(...LIGHT_GREY)
  const reasonBoxH = reasoningLines.length * 5 + 6
  doc.roundedRect(margin + 9, iy - 2, contentWidth - 18, reasonBoxH, 2, 2, 'F')
  setFont(doc, 7.5, 'normal', [70, 70, 70])
  doc.text(reasoningLines, margin + 13, iy + 3)
  iy += reasonBoxH + 4

  // warning
  if (warningLines.length) {
    setFont(doc, 7.5, 'italic', [180, 90, 10])
    doc.text(warningLines, margin + 9, iy)
    iy += warningLines.length * 5 + 3
  }

  // confidence bar
  setFont(doc, 7.5, 'normal', MID_GREY)
  doc.text('Confidence', margin + 9, iy + 3.5)
  const barX = margin + 38
  const barW = 50
  doc.setFillColor(220, 222, 228)
  doc.roundedRect(barX, iy, barW, 3, 1.5, 1.5, 'F')
  const [fr, fg, fb] = hexToRgb(getConfidenceColor(claim.confidence))
  doc.setFillColor(fr, fg, fb)
  doc.roundedRect(barX, iy, Math.max(barW * (claim.confidence || 0), 2), 3, 1.5, 1.5, 'F')
  setFont(doc, 7.5, 'normal', MID_GREY)
  doc.text(`${((claim.confidence || 0) * 100).toFixed(0)}%`, barX + barW + 4, iy + 3.5)

  return sy + blockH + 7
}

// ─── main export ─────────────────────────────────────────────────────────────

export async function generateVerificationPdf({ claims, statusConfig, summaryItems, fileName, logo, credibilityScore = 0, credibilityLabel = 'Unknown', credibilityColor = '#888888' }) {
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const margin = 14
  const contentWidth = pageWidth - margin * 2

  const logoBase64 = logo ? await loadImageAsBase64(logo) : null
  const headerCtx = { pageWidth, margin, logoBase64, fileName }

  // ── Cover page (no header/footer chrome)
  drawCoverPage(doc, { pageWidth, pageHeight, margin, contentWidth, logoBase64, fileName, credibilityScore, credibilityLabel, credibilityColor, summaryItems })

  // ── Category reference page
  drawCategoryPage(doc, { pageWidth, pageHeight, margin, contentWidth, logoBase64, fileName })

  // ── Claims pages — grouped by paper/source
  doc.addPage()
  drawHeader(doc, headerCtx)
  let y = 38

  const checkPageBreak = (needed) => {
    if (y + needed > pageHeight - 24) {
      doc.addPage()
      drawHeader(doc, headerCtx)
      y = 38
    }
  }

  // Group claims by authorLine (paper)
  const groups = {}
  claims.forEach(claim => {
    const key = claim.authorLine || 'Unknown Source'
    if (!groups[key]) groups[key] = []
    groups[key].push(claim)
  })

  Object.entries(groups).forEach(([paper, groupClaims]) => {
    checkPageBreak(18)
    y = drawSectionDivider(doc, { margin, contentWidth, y, title: `Paper: ${paper}` })

    groupClaims.forEach(claim => {
      const config = statusConfig[claim.status]
      const textLines = doc.splitTextToSize(`"${claim.text}"`, contentWidth - 22)
      const reasoningLines = doc.splitTextToSize(claim.reasoning || '', contentWidth - 22)
      const warningLines = claim.warning ? doc.splitTextToSize(claim.warning, contentWidth - 22) : []
      let blockH = 10 + textLines.length * 5 + 6 + reasoningLines.length * 5 + 6 + 10
      if (warningLines.length) blockH += warningLines.length * 5 + 5
      if (claim.doi) blockH += 6

      checkPageBreak(blockH)
      y = drawClaimCard(doc, { claim, config, margin, contentWidth, pageWidth, pageHeight, y, headerCtx, checkPageBreak })
    })

    y += 4
  })

  // ── Add footers to all pages except cover
  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 2; i <= totalPages; i++) {
    doc.setPage(i)
    drawFooter(doc, { pageWidth, pageHeight, margin, contentWidth, pageNum: i - 1, totalPages: totalPages - 1 })
  }

  doc.save(`verifai_report_${fileName.replace(/\.pdf$/i, '')}.pdf`)
}
