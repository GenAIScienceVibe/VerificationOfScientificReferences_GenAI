import jsPDF from 'jspdf'

const NAVY = [26, 58, 107]

const hexToRgb = (hex) => {
  const clean = hex.replace('#', '')
  const bigint = parseInt(clean, 16)
  return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255]
}

const loadImageAsBase64 = (url) =>
  new Promise((resolve, reject) => {
    const img = new window.Image()
    img.crossOrigin = 'Anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0)
      resolve(canvas.toDataURL('image/png'))
    }
    img.onerror = reject
    img.src = url
  })

const getConfidenceColor = (c) => {
  if (c > 0.7) return "#16a34a"
  if (c > 0.4) return "#d97706"
  return "#dc2626"
}

function drawHeader(doc, { pageWidth, margin, logoBase64, fileName }) {
  doc.setFillColor(255, 255, 255)
  doc.rect(0, 0, pageWidth, 32, 'F')

  if (logoBase64) {
    doc.addImage(logoBase64, 'PNG', margin, 6, 20, 20)
  }

  const textX = logoBase64 ? margin + 24 : margin
  doc.setTextColor(...NAVY)
  doc.setFont(undefined, 'bold')
  doc.setFontSize(15)
  doc.text('verifAi', textX, 16)

  doc.setFont(undefined, 'normal')
  doc.setFontSize(8.5)
  doc.setTextColor(140, 140, 140)
  doc.text(`Verification Report  ·  ${fileName}  ·  ${new Date().toLocaleDateString()}`, textX, 23)

  doc.setDrawColor(225, 225, 230)
  doc.setLineWidth(0.4)
  doc.line(margin, 32, pageWidth - margin, 32)
}

function drawFooter(doc, { pageWidth, pageHeight, margin, contentWidth, pageNum, totalPages }) {
  doc.setDrawColor(224, 224, 224)
  doc.setLineWidth(0.3)
  doc.line(margin, pageHeight - 22, pageWidth - margin, pageHeight - 22)

  doc.setFont(undefined, 'italic')
  doc.setFontSize(8)
  doc.setTextColor(140, 140, 140)
  const disclaimer = doc.splitTextToSize(
    'VerifAi uses AI-assisted analysis and automated source matching. Results may contain errors and accuracy is not guaranteed to be 100% — please verify critical claims against the original sources.',
    contentWidth - 28
  )
  doc.text(disclaimer, margin, pageHeight - 15)

  doc.setFont(undefined, 'normal')
  doc.setFontSize(8)
  doc.setTextColor(140, 140, 140)
  doc.text(`Page ${pageNum} / ${totalPages}`, pageWidth - margin, pageHeight - 15, { align: 'right' })
}

function drawCredibilityCard(doc, { margin, contentWidth, y }) {
  doc.setDrawColor(224, 224, 224)
  doc.setFillColor(248, 249, 251)
  doc.roundedRect(margin, y, contentWidth, 28, 3, 3, 'FD')
  doc.setFont(undefined, 'bold')
  doc.setFontSize(13)
  doc.setTextColor(...NAVY)
  doc.text('Credibility Score: 72% — Partially Reliable', margin + 8, y + 12)
  doc.setFont(undefined, 'normal')
  doc.setFontSize(9.5)
  doc.setTextColor(120, 120, 120)
  doc.text('Some claims are inaccurate or unsupported by their cited sources.', margin + 8, y + 21)
  return y + 38
}

function drawSummaryCard(doc, { margin, contentWidth, y, summaryItems }) {
  const totalClaims = summaryItems.reduce((sum, i) => sum + i.count, 0)
  const summaryCardHeight = 16 + summaryItems.length * 8 + 14

  doc.setDrawColor(224, 224, 224)
  doc.setFillColor(255, 255, 255)
  doc.roundedRect(margin, y, contentWidth, summaryCardHeight, 3, 3, 'FD')

  let sumY = y + 11
  doc.setFont(undefined, 'bold')
  doc.setFontSize(11)
  doc.setTextColor(30, 30, 30)
  doc.text('Fazit — Claims Summary', margin + 8, sumY)
  sumY += 9

  const colWidth = (contentWidth - 16) / 2
  summaryItems.forEach((item, idx) => {
    const col = idx % 2
    const row = Math.floor(idx / 2)
    const itemX = margin + 8 + col * colWidth
    const itemY = sumY + row * 8

    const [ir, ig, ib] = hexToRgb(item.color)
    doc.setFillColor(ir, ig, ib)
    doc.circle(itemX + 1.5, itemY - 1.5, 1.5, 'F')

    doc.setFont(undefined, 'normal')
    doc.setFontSize(9.5)
    doc.setTextColor(60, 60, 60)
    doc.text(item.label, itemX + 6, itemY)

    doc.setFont(undefined, 'bold')
    doc.setTextColor(20, 20, 20)
    doc.text(`${item.count}`, itemX + colWidth - 10, itemY, { align: 'right' })
  })

  sumY += Math.ceil(summaryItems.length / 2) * 8 + 4

  let barCursorX = margin + 8
  const stackBarWidth = contentWidth - 16
  summaryItems.forEach((item) => {
    const segWidth = (item.count / totalClaims) * stackBarWidth
    const [ir, ig, ib] = hexToRgb(item.color)
    doc.setFillColor(ir, ig, ib)
    doc.rect(barCursorX, sumY, segWidth, 4, 'F')
    barCursorX += segWidth
  })

  return y + summaryCardHeight + 10
}

function drawClaimCard(doc, { claim, config, margin, contentWidth, pageWidth, y }) {
  const [cr, cg, cb] = hexToRgb(config.color)
  const [bgr, bgg, bgb] = hexToRgb(config.bg)
  const [br, bgB, bb2] = hexToRgb(config.border)

  const textLines = doc.splitTextToSize(claim.text, contentWidth - 20)
  const reasoningLines = doc.splitTextToSize(`AI reasoning: ${claim.reasoning}`, contentWidth - 20)
  const warningLines = claim.warning ? doc.splitTextToSize(claim.warning, contentWidth - 20) : []

  let blockHeight = 16 + textLines.length * 5 + 6 + reasoningLines.length * 5 + 6
  if (claim.warning) blockHeight += warningLines.length * 5 + 6
  blockHeight += 12

  const startY = y

  doc.setDrawColor(br, bgB, bb2)
  doc.setFillColor(255, 255, 255)
  doc.roundedRect(margin, startY, contentWidth, blockHeight, 3, 3, 'FD')

  doc.setFillColor(cr, cg, cb)
  doc.roundedRect(margin, startY, 3.5, blockHeight, 1.5, 1.5, 'F')

  let innerY = startY + 9

  doc.setFont(undefined, 'bold')
  doc.setFontSize(9)
  doc.setTextColor(120, 120, 120)
  doc.text(`CLAIM ${claim.id}`, margin + 9, innerY)

  doc.setFontSize(8.5)
  const badgeWidth = doc.getTextWidth(config.label) + 10
  const badgeX = pageWidth - margin - badgeWidth - 6
  doc.setFillColor(bgr, bgg, bgb)
  doc.roundedRect(badgeX, innerY - 5, badgeWidth, 7, 3, 3, 'F')
  doc.setTextColor(cr, cg, cb)
  doc.text(config.label, badgeX + 5, innerY)

  innerY += 8

  doc.setFont(undefined, 'normal')
  doc.setFontSize(9.5)
  doc.setTextColor(40, 40, 40)
  doc.text(textLines, margin + 9, innerY)
  innerY += textLines.length * 5 + 4

  doc.setFont(undefined, 'italic')
  doc.setFontSize(8.5)
  doc.setTextColor(90, 90, 90)
  doc.text(reasoningLines, margin + 9, innerY)
  innerY += reasoningLines.length * 5 + 4

  if (claim.warning) {
    doc.setFont(undefined, 'normal')
    doc.setFontSize(8.5)
    doc.setTextColor(217, 119, 6)
    doc.text(warningLines, margin + 9, innerY)
    innerY += warningLines.length * 5 + 4
  }

  doc.setFont(undefined, 'normal')
  doc.setFontSize(8.5)
  doc.setTextColor(120, 120, 120)
  doc.text('Confidence', margin + 9, innerY + 4)

  const barX = margin + 38
  const barWidth = 40
  doc.setFillColor(224, 224, 224)
  doc.roundedRect(barX, innerY, barWidth, 3, 1.5, 1.5, 'F')
  const confHex = getConfidenceColor(claim.confidence)
  const [fr, fg, fb] = hexToRgb(confHex)
  doc.setFillColor(fr, fg, fb)
  doc.roundedRect(barX, innerY, Math.max(barWidth * claim.confidence, 2), 3, 1.5, 1.5, 'F')
  doc.setTextColor(120, 120, 120)
  doc.text(`${claim.confidence}`, barX + barWidth + 6, innerY + 4)

  return startY + blockHeight + 8
}

export async function generateVerificationPdf({ claims, statusConfig, summaryItems, fileName, logo }) {
  const doc = new jsPDF()
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const margin = 14
  const contentWidth = pageWidth - margin * 2

  let logoBase64 = null
  try {
    logoBase64 = await loadImageAsBase64(logo)
  } catch (e) {
    logoBase64 = null
  }

  const headerCtx = { pageWidth, margin, logoBase64, fileName }

  let y = 0
  drawHeader(doc, headerCtx)
  y = 42

  const checkPageBreak = (neededHeight) => {
    if (y + neededHeight > pageHeight - 28) {
      doc.addPage()
      drawHeader(doc, headerCtx)
      y = 42
    }
  }

  y = drawCredibilityCard(doc, { margin, contentWidth, y })

  const summaryCardHeight = 16 + summaryItems.length * 8 + 14
  checkPageBreak(summaryCardHeight)
  y = drawSummaryCard(doc, { margin, contentWidth, y, summaryItems })

  doc.setFont(undefined, 'bold')
  doc.setFontSize(11)
  doc.setTextColor(30, 30, 30)
  doc.text('Claims Overview', margin, y)
  y += 8

  claims.forEach((claim) => {
    const config = statusConfig[claim.status]

    const textLines = doc.splitTextToSize(claim.text, contentWidth - 20)
    const reasoningLines = doc.splitTextToSize(`AI reasoning: ${claim.reasoning}`, contentWidth - 20)
    const warningLines = claim.warning ? doc.splitTextToSize(claim.warning, contentWidth - 20) : []

    let blockHeight = 16 + textLines.length * 5 + 6 + reasoningLines.length * 5 + 6
    if (claim.warning) blockHeight += warningLines.length * 5 + 6
    blockHeight += 12

    checkPageBreak(blockHeight)

    y = drawClaimCard(doc, { claim, config, margin, contentWidth, pageWidth, y })
  })

  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i)
    drawFooter(doc, { pageWidth, pageHeight, margin, contentWidth, pageNum: i, totalPages })
  }

  doc.save(`verifai_report_${fileName.replace('.pdf', '')}.pdf`)
}