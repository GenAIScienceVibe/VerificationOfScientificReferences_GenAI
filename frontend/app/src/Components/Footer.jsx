import { useState } from 'react'
import logo from '../assets/Logo_VerifAi.png'
import Modal from './Modal'

function Footer() {
  const [openModal, setOpenModal] = useState(null)

  return (
    <>
      <footer style={{ background: "#f5f7fa", borderTop: "1px solid #e0e4ea", padding: "20px 80px 0" }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          maxWidth: "1200px", margin: "0 auto", gap: "48px", paddingBottom: "16px"
        }}>
          {/* Brand column */}
          <div style={{ flex: "0 0 auto" }}>
            <img src={logo} alt="verifAi logo" style={{ height: "200px", width: "200px", objectFit: "contain", display: "block" }} />
          </div>

          {/* VerifAi links */}
          <div style={{ textAlign: "left" }}>
            <p style={{ fontWeight: "700", marginBottom: "14px", color: "#111", fontSize: "13px", letterSpacing: "0.5px" }}>VERIFAI</p>
            <a onClick={() => setOpenModal('about')} style={{ display: "block", color: "#555", textDecoration: "none", marginBottom: "10px", fontSize: "14px", cursor: "pointer" }}>About</a>
            <a onClick={() => setOpenModal('contact')} style={{ display: "block", color: "#555", textDecoration: "none", fontSize: "14px", cursor: "pointer" }}>Contact Us</a>
          </div>

          {/* Legal links */}
          <div style={{ textAlign: "left" }}>
            <p style={{ fontWeight: "700", marginBottom: "14px", color: "#111", fontSize: "13px", letterSpacing: "0.5px" }}>LEGAL</p>
            <a onClick={() => setOpenModal('imprint')} style={{ display: "block", color: "#555", textDecoration: "none", marginBottom: "10px", fontSize: "14px", cursor: "pointer" }}>Imprint</a>
            <a onClick={() => setOpenModal('privacy')} style={{ display: "block", color: "#555", textDecoration: "none", fontSize: "14px", cursor: "pointer" }}>Privacy Policy</a>
          </div>

          {/* Socials */}
          <div style={{ textAlign: "left" }}>
            <p style={{ fontWeight: "700", marginBottom: "14px", color: "#111", fontSize: "13px", letterSpacing: "0.5px" }}>FOLLOW US</p>
            <a href="https://www.linkedin.com/school/tum-campus-heilbronn/posts/?feedView=all" target="_blank" rel="noreferrer" style={{ color: "#555", textDecoration: "none", fontSize: "14px", display: "flex", alignItems: "center", gap: "8px" }}>
              <svg width="18" height="18" viewBox="0 0 24 24">
                <rect width="24" height="24" rx="4" fill="#0a66c2"/>
                <path fill="white" d="M8.34 18.5H5.67V9.66h2.67v8.84zM7 8.48a1.55 1.55 0 1 1 0-3.1 1.55 1.55 0 0 1 0 3.1zM18.5 18.5h-2.67v-4.3c0-1.03-.02-2.35-1.43-2.35-1.43 0-1.65 1.12-1.65 2.28v4.37H10.1V9.66h2.56v1.2h.04c.36-.68 1.23-1.4 2.54-1.4 2.71 0 3.21 1.78 3.21 4.1v4.94z"/>
              </svg>
              LinkedIn
            </a>
          </div>
        </div>

        {/* Bottom bar */}
        <div style={{ borderTop: "1px solid #e0e4ea", maxWidth: "1200px", margin: "0 auto", padding: "16px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ color: "#aaa", fontSize: "12px", margin: 0 }}>© 2026 verifAi · Powered by TUM Campus Heilbronn</p>
        </div>
      </footer>

      {openModal === 'about' && (
        <Modal title="" onClose={() => setOpenModal(null)}>
          <div style={{ display: "flex", alignItems: "center", gap: "4px", marginBottom: "-10px" }}>
            <span style={{ fontSize: "22px", fontWeight: "700", color: "#111" }}>About</span>
            <img src={logo} alt="verifAi logo" style={{ height: "130px", marginLeft: "-20px" }} />
          </div>
          <p style={{ marginBottom: "16px" }}>Verify is an AI-assisted citation and evidence verification platform designed to support researchers, students, and academic professionals in evaluating the reliability of scientific references.</p>
          <p style={{ marginBottom: "16px" }}>In an era where AI-generated content is increasingly used for academic writing, ensuring the accuracy and validity of cited sources has become more important than ever. Verify helps users assess whether references are authentic, correctly cited, and supported by credible scientific evidence.</p>
          <p style={{ marginBottom: "16px" }}>By combining generative AI with automated verification methods, Verify streamlines the citation review process and promotes transparency, trust, and academic integrity. Our goal is to make evidence verification faster, more accessible, and more reliable for everyone working with scientific literature.</p>
          <p>Developed by a student team at the TUM Campus Heilbronn as part of the course Foundations and Applications of Generative AI, Verify addresses one of the key challenges of AI-assisted writing: maintaining confidence in the sources behind generated content.</p>
        </Modal>
      )}

{openModal === 'contact' && (
  <Modal title="Contact us" onClose={() => setOpenModal(null)}>
    <p>If you have any questions, feedback, or run into any issues, feel free to reach out to us at:</p>
    <a href="mailto:contact@tum.de" style={{ marginTop: "12px", display: "inline-block", fontWeight: "600", color: "#1a3a6b", textDecoration: "none" }}>contact@tum.de</a>
  </Modal>
)}

      {openModal === 'imprint' && (
        <Modal title="Imprint" onClose={() => setOpenModal(null)}>
          <p style={{ marginBottom: "16px", fontWeight: "600" }}>Information according to § 5 TMG</p>
          <p style={{ marginBottom: "4px" }}>[First name Last name]</p>
          <p style={{ marginBottom: "4px" }}>Technical University of Munich</p>
          <p style={{ marginBottom: "4px" }}>TUM Campus Heilbronn</p>
          <p style={{ marginBottom: "16px" }}>Bildungscampus 9, 74076 Heilbronn, Germany</p>

          <p style={{ marginBottom: "4px", fontWeight: "600" }}>Contact</p>
          <p style={{ marginBottom: "4px" }}>Email: [E-Mail]</p>
          <p style={{ marginBottom: "16px" }}>Phone: [Placeholder]</p>

          <p style={{ marginBottom: "4px", fontWeight: "600" }}>Responsible for content according to § 18 Para. 2 MStV</p>
          <p style={{ marginBottom: "16px" }}>[First name Last name], [Address as above]</p>

          <p style={{ marginBottom: "8px", fontWeight: "600" }}>Disclaimer</p>
          <p style={{ marginBottom: "16px" }}>This project was created as part of the course "Foundations and Applications of Generative AI" at TUM Campus Heilbronn and serves teaching and demonstration purposes only. Despite careful content control, we accept no liability for the content of external links.</p>
        </Modal>
      )}

      {openModal === 'privacy' && (
        <Modal title="Privacy Policy" onClose={() => setOpenModal(null)}>
          <p style={{ marginBottom: "16px", fontWeight: "600" }}>1. Data Controller</p>
          <p style={{ marginBottom: "16px" }}>[First name Last name], TUM Campus Heilbronn, Bildungscampus 9, 74076 Heilbronn. Contact: [E-Mail]</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>2. Collection and Processing of Data</p>
          <p style={{ marginBottom: "16px" }}>When uploading a document, the file is temporarily transmitted to our server and/or third-party APIs (e.g. AI models) for processing. Uploaded documents are stored for [Placeholder: insert retention period] and then deleted.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>3. Cookies and Tracking</p>
          <p style={{ marginBottom: "16px" }}>This website currently does not use any third-party tracking cookies or analytics tools. [Placeholder, should this change]</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>4. Your Rights</p>
          <p style={{ marginBottom: "16px" }}>You have the right to access, rectify, erase, and restrict the processing of your personal data under the GDPR. Please contact contact@verifai.com for any such requests.</p>

          <p>This is a student project for demonstration purposes; this privacy policy is a placeholder and should be reviewed legally before any productive use.</p>
        </Modal>
      )}
    </>
  )
}

export default Footer