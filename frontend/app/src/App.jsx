import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './Components/Header'
import Footer from './Components/Footer'
import UploadPage from './Components/UploadPage'
import LoadingPage from './Components/LoadingPage'
import ErrorPage from './Components/ErrorPage'
import ResultsPage from './Components/ResultsPage'
import HowItWorksPage from './Components/HowItWorksPage'
import background from './assets/background.png'

function App() {
  return (
    <BrowserRouter>
      <div style={{ position: "relative", minHeight: "100vh", width: "100%", display: "flex", flexDirection: "column" }}>

        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: "700px",
          backgroundImage: `url(${background})`,
          backgroundSize: "1200px auto",
          backgroundPosition: "center 80px",
          backgroundRepeat: "no-repeat",
          zIndex: 0
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: "700px",
          background: "rgba(245,245,245,0.92)",
          zIndex: 0
        }} />

        <div style={{ position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column" }}>
          <Header />
          <div style={{ flex: 1 }}>
            <Routes>
              <Route path="/" element={<UploadPage />} />
              <Route path="/loading" element={<LoadingPage />} />
              <Route path="/error" element={<ErrorPage />} />
              <Route path="/results" element={<ResultsPage />} />
              <Route path="/how-it-works" element={<HowItWorksPage />} />
            </Routes>
          </div>
        </div>

        <div style={{ position: "relative", zIndex: 1 }}>
          <Footer />
        </div>
      </div>
    </BrowserRouter>
  )
}

export default App