import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

function UploadPage() {
  const navigate = useNavigate()
  const [showReferenceUpload, setShowReferenceUpload] = useState(false)
  const [referenceFiles, setReferenceFiles] = useState([])

  const handleReferenceFiles = (e) => {
    const files = Array.from(e.target.files)
    setReferenceFiles(prev => [...prev, ...files])
  }

  const removeReferenceFile = (index) => {
    setReferenceFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleFileSelected = (e) => {
    const file = e.target.files[0]
    if (!file) return

    navigate('/loading', {
      state: { file, fileName: file.name, referenceFiles }
    })
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
  backgroundPosition: "center 80%",
  backgroundRepeat: "no-repeat"
}}>
    <div style={{
  position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
  background: "rgba(245,245,245,0.9)"
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

        <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-start", marginBottom: "56px", maxWidth: "700px", margin: "0 auto 56px" }}>
  {[
    { id: 1, label: "Upload your PDF" },
    { id: 2, label: "We fetch every cited source" },
    { id: 3, label: "AI checks each claim" },
    { id: 4, label: "Get a full report" },
  ].map((step, i) => (
    <div key={step.id} style={{ display: "flex", alignItems: "flex-start", flex: i < 3 ? 1 : "0 0 auto" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "52px" }}>
        <div style={{
          width: "52px", height: "52px", borderRadius: "50%",
          background: "#1a3a6b", color: "white",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: "700", fontSize: "18px", flexShrink: 0
        }}>
          {step.id}
        </div>
        <span style={{ fontSize: "13px", color: "#555", lineHeight: "1.5", textAlign: "center", marginTop: "14px", width: "110px" }}>
          {step.label}
        </span>
      </div>
      {i < 3 && <div style={{ flex: 1, height: "2px", background: "#c5cfe0", marginTop: "26px" }} />}
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
            onChange={handleFileSelected}
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

        {/* Optional: upload additional reference documents */}
        <div style={{
          background: "white", borderRadius: "16px", padding: "24px 32px",
          maxWidth: "600px", margin: "20px auto 0", boxShadow: "0 2px 16px rgba(0,0,0,0.07)",
          textAlign: "left"
        }}>
          <button
            onClick={() => setShowReferenceUpload(prev => !prev)}
            style={{
              width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
              background: "none", border: "none", cursor: "pointer", padding: 0
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span style={{ fontSize: "18px", width: "20px", flexShrink: 0, textAlign: "center" }}>📎</span>
              <div style={{ textAlign: "left", marginLeft: "8px" }}>
                <p style={{ fontWeight: "600", fontSize: "15px", color: "#111", margin: 0 }}>
                  Add reference documents
                </p>
                <p style={{ color: "#888", fontSize: "13px", margin: "2px 0 0" }}>
                  Optional — for sources we can't access automatically
                </p>
              </div>
            </div>
            <span style={{
              fontSize: "20px", color: "#1a3a6b",
              transform: showReferenceUpload ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 0.2s"
            }}>
              ⌄
            </span>
          </button>

          {showReferenceUpload && (
            <div style={{ marginTop: "20px", borderTop: "1px solid #eee", paddingTop: "20px" }}>
              <p style={{ color: "#888", fontSize: "13px", lineHeight: "1.6", marginBottom: "16px" }}>
                VerifAi automatically retrieves cited sources via open-access identifiers (DOI/CrossRef).
                If a citation can't be resolved this way, you can upload a PDF of that source here — for
                example a paper you already have access to — so we can still compare the claim against it.
              </p>

              <input
                type="file"
                accept=".pdf"
                id="referenceInput"
                multiple
                style={{ display: "none" }}
                onChange={handleReferenceFiles}
              />

              <button
                onClick={() => document.getElementById('referenceInput').click()}
                style={{
                  background: "white", border: "1px dashed #c5cfe0", borderRadius: "8px",
                  padding: "14px", cursor: "pointer", fontSize: "14px", width: "100%",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", color: "#1a3a6b"
                }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                Add reference PDF(s)
              </button>

              {referenceFiles.length > 0 && (
                <div style={{ marginTop: "14px", display: "flex", flexDirection: "column", gap: "8px" }}>
                  {referenceFiles.map((file, i) => (
                    <div key={i} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      background: "#f5f5f5", borderRadius: "6px", padding: "8px 12px", fontSize: "13px"
                    }}>
                      <span style={{ color: "#444", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        📄 {file.name}
                      </span>
                      <button
                        onClick={() => removeReferenceFile(i)}
                        style={{ background: "none", border: "none", color: "#aaa", cursor: "pointer", fontSize: "14px" }}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}

export default UploadPage