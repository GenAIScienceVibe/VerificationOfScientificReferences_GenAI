import { Link, useLocation, useNavigate } from 'react-router-dom'
import logo from '../assets/Logo_VerifAi.png'

function Header() {
  const location = useLocation()
  const navigate = useNavigate()
  const onHowItWorks = location.pathname === '/how-it-works'
  const onResults = location.pathname === '/results'
  const onLoading = location.pathname === '/loading'
  const headerBg = (onResults || onLoading || onHowItWorks) ? "#f5f5f5" : "transparent"

  return (
    <header style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "0px 64px", background: headerBg,
      position: "relative", zIndex: 10
    }}>
      <Link to="/">
        <img src={logo} alt="verifAi logo" style={{ height: "110px", cursor: "pointer" }} />
      </Link>
      <nav>
        {onHowItWorks ? (
          <button
            onClick={() => navigate(-1)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "#1a3a6b", fontSize: "15px", fontWeight: "500", padding: 0 }}
          >
            Verify PDF
          </button>
        ) : (
          <Link to="/how-it-works" style={{ color: "#1a3a6b", textDecoration: "none", fontSize: "15px", fontWeight: "500" }}>How it works</Link>
        )}
      </nav>
    </header>
  )
}

export default Header
