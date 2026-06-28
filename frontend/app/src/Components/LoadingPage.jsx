import { useNavigate, useLocation } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { getDocumentStatus, TERMINAL_SUCCESS_STATUSES, TERMINAL_FAILURE_STATUSES } from '../api'

function LoadingPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const fileName = location.state?.fileName || "research_paper.pdf"
  const documentId = location.state?.documentId

  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState(0)
  const pollRef = useRef(null)

  const steps = [
    { id: 1, label: "Reading PDF" },
    { id: 2, label: "Extracting claims" },
    { id: 3, label: "Checking sources" },
    { id: 4, label: "Preparing report" },
  ]

  useEffect(() => {
    if (!documentId) {
      navigate('/error')
      return
    }

    const poll = async () => {
      try {
        const status = await getDocumentStatus(documentId)
        const pct = status.progress_percentage ?? 0
        setProgress(pct)

        if (TERMINAL_SUCCESS_STATUSES.includes(status.status) || pct >= 100) {
          clearInterval(pollRef.current)
          setProgress(100)
          setTimeout(() => navigate('/results', { state: { fileName, documentId } }), 500)
        } else if (TERMINAL_FAILURE_STATUSES.includes(status.status)) {
          clearInterval(pollRef.current)
          navigate('/error')
        }
      } catch (err) {
        clearInterval(pollRef.current)
        navigate('/error')
      }
    }

    poll()
    pollRef.current = setInterval(poll, 2000)

    return () => clearInterval(pollRef.current)
  }, [documentId, navigate, fileName])

  useEffect(() => {
    if (progress < 25) setCurrentStep(0)
    else if (progress < 50) setCurrentStep(1)
    else if (progress < 75) setCurrentStep(2)
    else setCurrentStep(3)
  }, [progress])

  const getStatus = (i) => {
    if (i === 0) {
      return progress >= (100/3) ? "done" : "active"
    }
    const segmentSize = 100 / 3
    const lineEnd = i * segmentSize
    if (progress >= lineEnd) return "done"
    return "pending"
  }

  const getLineWidth = (lineIndex) => {
    const segmentSize = 100 / 3
    const start = lineIndex * segmentSize
    const end = start + segmentSize
    if (progress <= start) return "0%"
    if (progress >= end) return "100%"
    return `${((progress - start) / segmentSize) * 100}%`
  }

  return (
    <div style={{
      display: "flex", justifyContent: "center",
      padding: "20px 24px 80px",
      marginTop: "-80px",
      paddingTop: "80px",
      position: "relative",
      backgroundImage: `url('/src/assets/background.png')`,
      backgroundSize: "60%",
      backgroundPosition: "center 350px",
      backgroundRepeat: "no-repeat"
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        background: "rgba(245,245,245,0.9)"
      }} />

      <div style={{ background: "white", borderRadius: "16px", padding: "48px 56px", maxWidth: "600px", width: "100%", textAlign: "center", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", position: "relative", zIndex: 1 }}>

        <div style={{ marginBottom: "24px" }}>
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="12" y="8" width="40" height="52" rx="4" fill="#e8edf5" stroke="#c5cfe0" strokeWidth="1.5"/>
            <line x1="20" y1="22" x2="44" y2="22" stroke="#a0aec0" strokeWidth="2" strokeLinecap="round"/>
            <line x1="20" y1="30" x2="44" y2="30" stroke="#a0aec0" strokeWidth="2" strokeLinecap="round"/>
            <line x1="20" y1="38" x2="36" y2="38" stroke="#a0aec0" strokeWidth="2" strokeLinecap="round"/>
            <circle cx="52" cy="52" r="14" fill="white" stroke="#c5cfe0" strokeWidth="1.5"/>
            <circle cx="52" cy="50" r="7" fill="none" stroke="#1a3a6b" strokeWidth="2"/>
            <line x1="57" y1="55" x2="63" y2="61" stroke="#1a3a6b" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M49 48 L51 50 L55 46" stroke="#f5a623" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>

        <h2 style={{ fontWeight: "700", fontSize: "28px", marginBottom: "12px", color: "#111" }}>
          Verifying your document
        </h2>

        <span style={{ background: "#f0f2f5", borderRadius: "20px", padding: "6px 16px", fontSize: "13px", color: "#444", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          📄 {fileName}
        </span>

        <p style={{ color: "#888", margin: "20px 0 28px", fontSize: "15px", lineHeight: "1.6" }}>
          We're checking whether each claim is truly supported by its cited source.
        </p>

        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "36px" }}>
          <div style={{ flex: 1, background: "#e0e0e0", borderRadius: "99px", height: "8px" }}>
            <div style={{ width: `${progress}%`, background: "#1a3a6b", borderRadius: "99px", height: "8px", transition: "width 0.3s ease" }} />
          </div>
          <span style={{ fontSize: "15px", fontWeight: "600", color: "#111", minWidth: "40px" }}>{progress}%</span>
        </div>

        <div style={{ display: "flex", alignItems: "flex-start", marginBottom: "36px", justifyContent: "space-between" }}>
          {steps.map((step, i) => (
            <div key={step.id} style={{ display: "flex", alignItems: "flex-start", flex: i < steps.length - 1 ? 1 : "0 0 40px" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "40px" }}>
                <div style={{
                  width: "40px", height: "40px", borderRadius: "50%", border: "2px solid",
                  borderColor: getStatus(i) === "pending" ? "#ccc" : "#1a3a6b",
                  background: getStatus(i) === "done" ? "#1a3a6b" : "white",
                  color: getStatus(i) === "done" ? "white" : getStatus(i) === "active" ? "#1a3a6b" : "#ccc",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: "700", fontSize: "15px", flexShrink: 0
                }}>
                  {getStatus(i) === "done" ? "✓" : step.id}
                </div>
                <span style={{ fontSize: "12px", fontWeight: "600", marginTop: "10px", color: "#222", textAlign: "center", width: "80px" }}>{step.label}</span>
                <span style={{ fontSize: "11px", color: getStatus(i) === "active" ? "#1a3a6b" : "#999", marginTop: "2px", textAlign: "center" }}>
                  {getStatus(i) === "done" ? "Completed" : getStatus(i) === "active" ? "In progress" : "Pending"}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div style={{ flex: 1, height: "2px", background: "#e0e0e0", position: "relative", overflow: "hidden", marginTop: "19px" }}>
                  <div style={{
                    position: "absolute", top: 0, left: 0, height: "2px",
                    background: "#1a3a6b",
                    width: getLineWidth(i),
                    transition: "width 0.3s ease"
                  }} />
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{ background: "#eef2ff", borderRadius: "10px", padding: "14px 18px", marginBottom: "20px", fontSize: "13px", color: "#444", display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ width: "20px", height: "20px", borderRadius: "50%", background: "#1a3a6b", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px", fontWeight: "700", flexShrink: 0 }}>i</div>
          No need to refresh - your report will appear automatically.
        </div>

        <button onClick={() => navigate('/')} style={{ border: "1px solid #ccc", background: "white", borderRadius: "10px", padding: "12px 28px", cursor: "pointer", fontSize: "14px", color: "#444" }}>
          ✕ Cancel and upload another file
        </button>

      </div>
    </div>
  )
}

export default LoadingPage 