import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import LightReport from './pages/LightReport.jsx'
import Map from './pages/Map.jsx'
import Processing from './pages/Processing.jsx'
import Results from './pages/Results.jsx'
import Upload from './pages/Upload.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/processing/:jobId" element={<Processing />} />
        <Route path="/results/:jobId" element={<Results />} />
        <Route path="/map" element={<Map />} />
        <Route path="/light-report" element={<LightReport />} />
      </Routes>
    </BrowserRouter>
  )
}
