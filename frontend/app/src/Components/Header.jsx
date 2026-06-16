import logo from '../assets/Logo_VerifAi.png'

function Header() {
  return (
    <header style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "8px 64px 0px 64px", background: "transparent",
      position: "relative", zIndex: 10
    }}>
<img src={logo} alt="verifAi logo" style={{ height: "80px", filter: "brightness(1)" }} />      <nav>
        <a href="#" style={{ color: "#1a3a6b", textDecoration: "none", fontSize: "15px", fontWeight: "500" }}>How it works</a>
      </nav>
    </header>
  )
}

export default Header