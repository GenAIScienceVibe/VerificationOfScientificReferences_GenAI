import { Link } from 'react-router-dom'
import logo from '../assets/Logo_VerifAi.png'

function Header() {
  return (
    <header style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "0px 64px", background: "transparent",
      position: "relative", zIndex: 10
    }}>
      <Link to="/">
        <img src={logo} alt="verifAi logo" style={{ height: "120px", cursor: "pointer", marginTop: "-20px", marginBottom: "-20px" }} />
      </Link>
      <nav>
        <a href="#" style={{ color: "#1a3a6b", textDecoration: "none", fontSize: "16px", fontWeight: "500" }}>How it works</a>
      </nav>
    </header>
  )
}

export default Header