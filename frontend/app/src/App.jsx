import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './Components/Header'
import Footer from './Components/Footer'
import UploadPage from './Components/UploadPage'
import LoadingPage from './Components/LoadingPage'
import ErrorPage from './Components/ErrorPage'
import ResultsPage from './Components/ResultsPage'
import HowItWorksPage from './Components/HowItWorksPage'
import CitationGraph from './Components/CitationGraph'

function App() {
  return (
    <BrowserRouter>
      <div style={{ position: "relative", minHeight: "100vh", width: "100%", display: "flex", flexDirection: "column" }}>

        <div style={{ position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column" }}>
          <Header />
          <div style={{ flex: 1 }}>
            <Routes>
              <Route path="/" element={<UploadPage />} />
              <Route path="/loading" element={<LoadingPage />} />
              <Route path="/error" element={<ErrorPage />} />
              <Route path="/results" element={<ResultsPage />} />
              <Route path="/how-it-works" element={<HowItWorksPage />} />
              <Route path="/citation-graph" element={<CitationGraph />} />
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
