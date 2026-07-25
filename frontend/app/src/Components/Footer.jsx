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
          

          {/* Other links */}
          <div style={{ textAlign: "left" }}>
            <p style={{ fontWeight: "700", marginBottom: "14px", color: "#111", fontSize: "13px", letterSpacing: "0.5px" }}>LEGAL</p>
            <a onClick={() => setOpenModal('imprint')} style={{ display: "block", color: "#555", textDecoration: "none", marginBottom: "10px", fontSize: "14px", cursor: "pointer" }}>Imprint</a>
            <a onClick={() => setOpenModal('privacy')} style={{ display: "block", color: "#555", textDecoration: "none", fontSize: "14px", cursor: "pointer" }}>Privacy Policy</a>
          </div>

          
          {/* Social Links */}
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

        
        {/* Bottom  */}
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
          <p style={{ marginBottom: "16px", fontSize: "12px", color: "#888" }}>Last updated: July 2025</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>1. Data Controller</p>
          <p style={{ marginBottom: "16px" }}>The responsible party for data processing on this platform is the student project team of <em>verifAi</em>, developed at the Technical University of Munich, TUM Campus Heilbronn, Bildungscampus 9, 74076 Heilbronn, Germany. For data-related inquiries, please contact us at <a href="mailto:contact@tum.de" style={{ color: "#1a3a6b" }}>contact@tum.de</a>.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>2. Scope and Purpose of Data Processing</p>
          <p style={{ marginBottom: "16px" }}>verifAi is an AI-assisted academic citation verification tool. When you upload a document, the file content is transmitted to our backend servers and to third-party AI APIs solely for the purpose of automated citation and evidence verification. No personal data beyond the uploaded document content is collected. Documents are processed transiently and are not retained after the verification session ends.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>3. Third-Party Services</p>
          <p style={{ marginBottom: "16px" }}>To provide its core functionality, verifAi uses third-party AI services (including large language model APIs) to analyze document content. Uploaded content may be transmitted to these services for processing in accordance with their respective privacy policies. We recommend not uploading documents containing sensitive personal or confidential information.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>4. Cookies and Tracking</p>
          <p style={{ marginBottom: "16px" }}>This platform does not use third-party tracking cookies or analytics services. Local browser storage (localStorage) is used solely to preserve your in-session preferences (such as manual verdict overrides) and is never transmitted to our servers.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>5. Legal Basis</p>
          <p style={{ marginBottom: "16px" }}>Data processing is carried out on the basis of your explicit consent at the time of upload (Art. 6(1)(a) GDPR) and on the basis of legitimate interest in providing the requested service (Art. 6(1)(f) GDPR).</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>6. Your Rights under GDPR</p>
          <p style={{ marginBottom: "16px" }}>As a data subject, you have the right to access, rectification, erasure, restriction of processing, data portability, and the right to object to processing of your personal data. You also have the right to lodge a complaint with a supervisory authority. To exercise any of these rights, please contact us at <a href="mailto:contact@tum.de" style={{ color: "#1a3a6b" }}>contact@tum.de</a>.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>7. Data Retention</p>
          <p style={{ marginBottom: "16px" }}>Uploaded documents and derived verification results are retained only for the duration of the active session and are deleted thereafter. No document data is stored permanently on our servers.</p>

          <p style={{ marginBottom: "16px", fontWeight: "600" }}>8. Academic and Demonstration Context</p>
          <p style={{ color: "#666", fontSize: "13px", lineHeight: "1.6" }}>verifAi was developed as part of the course <em>Foundations and Applications of Generative AI</em> at TUM Campus Heilbronn. It is intended for academic demonstration purposes. While we have made reasonable efforts to ensure GDPR compliance, this policy has not been formally reviewed by a legal professional and should not be relied upon for commercially deployed services.</p>
        </Modal>
      )}
    </>
  )
}

export default Footer
