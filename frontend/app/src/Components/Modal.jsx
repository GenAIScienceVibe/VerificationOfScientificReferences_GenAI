function Modal({ title, children, onClose }) {
  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.4)", display: "flex",
      alignItems: "center", justifyContent: "center", zIndex: 1000
    }} onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white", borderRadius: "16px", padding: "32px 40px",
          maxWidth: "640px", width: "90%", position: "relative",
          boxShadow: "0 10px 40px rgba(0,0,0,0.2)", maxHeight: "80vh", overflowY: "auto"
        }}>
        <button
          onClick={onClose}
          style={{
            position: "absolute", top: "16px", right: "16px",
            background: "none", border: "none", cursor: "pointer",
            fontSize: "20px", color: "#888", width: "32px", height: "32px",
            borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center"
          }}>
          ✕
        </button>
        {title && <h2 style={{ fontSize: "22px", fontWeight: "700", color: "#111", marginBottom: "16px" }}>{title}</h2>}
        <div style={{ color: "#555", fontSize: "15px", lineHeight: "1.7" }}>{children}</div>
      </div>
    </div>
  )
}

export default Modal