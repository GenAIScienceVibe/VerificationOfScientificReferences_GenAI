import { useNavigate } from 'react-router-dom'

function ErrorPage() {
  const navigate = useNavigate()

  return (
<div style={{ background: "#f5f5f5", display: "flex", justifyContent: "center", padding: "40px 24px 80px" }}>      <div style={{ background: "white", borderRadius: "16px", padding: "48px 56px", maxWidth: "600px", width: "100%", textAlign: "center", boxShadow: "0 2px 16px rgba(0,0,0,0.07)" }}>

        <div style={{ marginBottom: "24px" }}>
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
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
          Something went wrong
        </h2>

        <p style={{ color: "#888", margin: "0 0 28px", fontSize: "15px" }}>
          We couldn't verify this document...
        </p>

        <hr style={{ border: "none", borderTop: "1px solid #e0e0e0", marginBottom: "28px" }} />

        <div style={{ display: "flex", justifyContent: "center", gap: "16px" }}>
          <button
            onClick={() => navigate('/loading')}
            style={{
              background: "#1a3a6b", color: "white", border: "none",
              borderRadius: "10px", padding: "12px 24px", cursor: "pointer",
              fontSize: "14px", fontWeight: "600", display: "flex", alignItems: "center", gap: "8px"
            }}>
            ↻ Try again
          </button>
          <button
            onClick={() => navigate('/')}
            style={{
              background: "white", color: "#444", border: "1px solid #ccc",
              borderRadius: "10px", padding: "12px 24px", cursor: "pointer",
              fontSize: "14px", display: "flex", alignItems: "center", gap: "8px"
            }}>
            ↑ Upload new file
          </button>
        </div>

      </div>
    </div>
  )
}

export default ErrorPage