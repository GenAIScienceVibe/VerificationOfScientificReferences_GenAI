import logo from '../assets/Logo_VerifAi.png'

function Footer() {
  return (
    <footer style={{ background: "#e8edf2", padding: "12px 80px 8px" }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        maxWidth: "1000px", margin: "0 auto", marginBottom: "0px"
      }}>
<img src={logo} alt="verifAi logo" style={{ height: "300px", marginTop: "-60px", marginBottom: "-60px" }} />        <div style={{ textAlign: "left" }}>
          <p style={{ fontWeight: "600", marginBottom: "12px", color: "#111", fontSize: "15px" }}>Quick links</p>
          <a href="#" style={{ display: "block", color: "#1a3a6b", textDecoration: "none", marginBottom: "12px", fontSize: "14px" }}>About</a>
          <a href="#" style={{ display: "block", color: "#1a3a6b", textDecoration: "none", fontSize: "14px" }}>Contact Us</a>
        </div>
        <div style={{ textAlign: "left" }}>
          <p style={{ fontWeight: "600", marginBottom: "12px", color: "#111", fontSize: "15px" }}>Socials</p>
          <a href="#" style={{ color: "#1a3a6b", textDecoration: "none", fontSize: "14px" }}>LinkedIn</a>
        </div>
      </div>
      <p style={{ textAlign: "center", color: "#999", fontSize: "12px" }}>2026, Powered by TUM</p>
    </footer>
  )
}

export default Footer