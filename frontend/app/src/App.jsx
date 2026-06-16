import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './Components/Header'
import Footer from './Components/Footer'
import UploadPage from './Components/UploadPage'
import LoadingPage from './Components/LoadingPage'
import ErrorPage from './Components/ErrorPage'
import ResultsPage from './Components/ResultsPage'

function App() {
  return (
    <BrowserRouter>
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", width: "100vw", padding: 0, margin: 0 }}>
        <Routes>
          <Route path="/" element={<><Header /><UploadPage /><Footer /></>} />
          <Route path="/loading" element={<><Header /><LoadingPage /><Footer /></>} />
          <Route path="/error" element={<><Header /><ErrorPage /><Footer /></>} />
          <Route path="/results" element={<><Header /><ResultsPage /><Footer /></>} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App