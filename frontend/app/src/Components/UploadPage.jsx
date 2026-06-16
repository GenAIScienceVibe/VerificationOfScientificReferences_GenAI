import { useNavigate } from 'react-router-dom'

function UploadPage() {
  const navigate = useNavigate()

  return (
   <div style={{
  display: "flex", justifyContent: "center",
  padding: "20px 24px 80px",
  marginTop: "-80px",
  paddingTop: "80px",
  position: "relative",
  backgroundImage: `url('/src/assets/background.png')`,
  backgroundSize: "60%",
  backgroundPosition: "center 80%",
  backgroundRepeat: "no-repeat"
}}>
    <div style={{
  position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
  background: "rgba(245,245,245,0.83)"
}} />

      <div style={{ maxWidth: "900px", width: "100%", textAlign: "center", position: "relative", zIndex: 1 }}>

        <span style={{ background: "#dbeafe", color: "#1a3a6b", borderRadius: "20px", padding: "6px 16px", fontSize: "13px", fontWeight: "600" }}>
          AI - Powered Verification
        </span>

        <h1 style={{ fontWeight: "800", fontSize: "42px", color: "#111", margin: "24px 0 16px" }}>
          Are your citations actually legit?
        </h1>

        <p style={{ color: "#888", fontSize: "16px", marginBottom: "56px", lineHeight: "1.8" }}>
          Upload a research paper or text, and we'll automatically check whether each claim is truly supported by its cited source.
        </p>

        <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", marginBottom: "56px" }}>
          {[
            { id: 1, label: "Upload your PDF" },
            { id: 2, label: "We fetch every cited source" },
            { id: 3, label: "AI checks each claim" },
            { id: 4, label: "Get a full report" },
          ].map((step, i) => (
            <div key={step.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
                {i > 0 && <div style={{ flex: 1, height: "2px", background: "#c5cfe0" }} />}
                <div style={{
                  width: "52px", height: "52px", borderRadius: "50%",
                  background: "#1a3a6b", color: "white",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: "700", fontSize: "18px", flexShrink: 0
                }}>
                  {step.id}
                </div>
                {i < 3 && <div style={{ flex: 1, height: "2px", background: "#c5cfe0" }} />}
              </div>
              <div style={{ width: "100%", marginTop: "14px", textAlign: "center" }}>
                <span style={{ fontSize: "13px", color: "#555", lineHeight: "1.5", display: "block" }}>
                  {step.label}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div style={{
          background: "white", borderRadius: "16px", padding: "60px 48px",
          maxWidth: "600px", margin: "0 auto", boxShadow: "0 2px 16px rgba(0,0,0,0.07)"
        }}>
          <div style={{ marginBottom: "16px" }}>
            <svg width="56" height="56" viewBox="0 0 48 48" fill="none">
              <path d="M24 32V20M24 20L18 26M24 20L30 26" stroke="#1a3a6b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M12 35C8 35 5 32 5 28C5 24.5 7.5 21.5 11 21C11 16 15 12 20 12C23 12 25.5 13.5 27 16C27.5 16 28 16 28.5 16C33 16 37 20 37 24.5C40 25 43 28 43 31.5C43 35 40 38 36 38H12V35Z" stroke="#1a3a6b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>

          <p style={{ fontWeight: "700", fontSize: "20px", color: "#111", marginBottom: "10px" }}>
            Drop your PDF here
          </p>
          <p style={{ color: "#888", fontSize: "15px", marginBottom: "28px" }}>
            or click to browse your files
          </p>

          <input
            type="file"
            accept=".pdf"
            id="fileInput"
            style={{ display: "none" }}
            onChange={() => navigate('/loading')}
          />

          <button
            onClick={() => document.getElementById('fileInput').click()}
            style={{
              background: "white", border: "1px solid #ccc", borderRadius: "8px",
              padding: "12px 28px", cursor: "pointer", fontSize: "15px",
              display: "inline-flex", alignItems: "center", gap: "8px", color: "#444"
            }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            Browse files
          </button>

          <p style={{ color: "#aaa", fontSize: "12px", marginTop: "16px" }}>PDF only</p>
        </div>

      </div>
    </div>
  )
}

export default UploadPage