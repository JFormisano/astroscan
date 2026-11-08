import { useEffect, useState } from 'react'
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import StarField from './components/StarField.jsx'
import Demo from './pages/Demo.jsx'
import Landing from './pages/Landing.jsx'
import LightReport from './pages/LightReport.jsx'
import Map from './pages/Map.jsx'
import Processing from './pages/Processing.jsx'
import Results from './pages/Results.jsx'
import Upload from './pages/Upload.jsx'
import './styles/sky.css'

function motionReduced() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function BackButton() {
  const navigate = useNavigate()
  const location = useLocation()

  function goBack() {
    // A page opened from a link has no in-app history. Send that visit home.
    if (location.key === 'default') navigate('/')
    else navigate(-1)
  }

  return (
    <div className="back-bar">
      <button type="button" className="back-btn" onClick={goBack}>
        <span aria-hidden="true">←</span>
        Back
      </button>
    </div>
  )
}

function SkyShell({ reduced }) {
  const { pathname } = useLocation()

  return (
    <>
      <StarField animate={!reduced} />
      <div className="sky-app">
        {pathname !== '/' && <BackButton />}
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/processing/:jobId" element={<Processing />} />
          <Route path="/results/:jobId" element={<Results />} />
          <Route path="/demo/:name" element={<Demo />} />
          <Route path="/map" element={<Map />} />
          <Route path="/light-report" element={<LightReport />} />
        </Routes>
      </div>
    </>
  )
}

export default function App() {
  const [reduced, setReduced] = useState(motionReduced)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return (
    <BrowserRouter>
      <SkyShell reduced={reduced} />
    </BrowserRouter>
  )
}
