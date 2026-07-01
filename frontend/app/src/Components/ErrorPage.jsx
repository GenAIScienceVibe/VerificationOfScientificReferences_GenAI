import { useNavigate, useLocation } from 'react-router-dom'
import Mascot from './Mascot.jsx'

function ErrorPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const file = location.state?.file
  const fileName = location.state?.fileName

  const handleTryAgain = () => {
    if (file) {
      navigate('/loading', { state: { file, fileName: fileName || file.name } })
    } else {
      navigate('/')
    }
  }

  return (
    <div style={{
  display: "flex", justifyContent: "center",
  padding: "20px 24px 80px",
  position: "relative",
  backgroundImage: `url('/src/assets/background.png')`,
  backgroundSize: "60%",
  backgroundPosition: "center 350px",
  backgroundRepeat: "no-repeat",
  minHeight: "600px"
}}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        background: "rgba(245,245,245,0.9)"
      }} />

      <div style={{ background: "white", borderRadius: "16px", padding: "48px 56px", maxWidth: "600px", width: "100%", textAlign: "center", boxShadow: "0 2px 16px rgba(0,0,0,0.07)", position: "relative", zIndex: 1 }}>

        <div style={{ display: "flex", justifyContent: "center", marginBottom: "24px" }}>
          <Mascot mood="sad" size={80} />
        </div>

        <h2 style={{ fontWeight: "700", fontSize: "28px", marginBottom: "12px", color: "#111" }}>
          Something went wrong
        </h2>

        <p style={{ color: "#888", margin: "0 0 28px", fontSize: "15px", lineHeight: "1.6" }}>
          We ran into a problem while verifying your document. This can happen if the file is too large, the backend timed out, or the document couldn't be parsed. You can try again or upload a different file.
        </p>

        <hr style={{ border: "none", borderTop: "1px solid #e0e0e0", marginBottom: "28px" }} />

        <div style={{ display: "flex", justifyContent: "center", gap: "16px" }}>
          {file && (
            <button
              onClick={handleTryAgain}
              style={{
                background: "#1a3a6b", color: "white", border: "none",
                borderRadius: "10px", padding: "12px 24px", cursor: "pointer",
                fontSize: "14px", fontWeight: "600", transition: "background 0.15s"
              }}
              onMouseEnter={e => e.currentTarget.style.background = '#0f2a5a'}
              onMouseLeave={e => e.currentTarget.style.background = '#1a3a6b'}>
              Try again
            </button>
          )}
          <button
            onClick={() => navigate('/')}
            style={{
              background: "white", color: "#444", border: "1px solid #ccc",
              borderRadius: "10px", padding: "12px 24px", cursor: "pointer",
              fontSize: "14px"
            }}>
            Upload new file
          </button>
        </div>

      </div>
    </div>
  )
}

export default ErrorPage