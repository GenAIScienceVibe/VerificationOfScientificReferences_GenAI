import { useNavigate } from 'react-router-dom'
import Mascot from './Mascot.jsx'

function ErrorPage() {
  const navigate = useNavigate()

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
              fontSize: "14px", fontWeight: "600"
            }}>
            Try again
          </button>
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