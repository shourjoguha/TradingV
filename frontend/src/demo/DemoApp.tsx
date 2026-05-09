import { Routes, Route, Navigate } from 'react-router-dom'
import { DemoLayout } from './components/DemoLayout'
import { DemoHome } from './pages/DemoHome'
import { DemoPredictions } from './pages/DemoPredictions'
import { DemoMotion } from './pages/DemoMotion'
import { DemoAbout } from './pages/DemoAbout'

export function DemoApp() {
  return (
    <DemoLayout>
      <Routes>
        <Route path="/" element={<DemoHome />} />
        <Route path="/predictions" element={<DemoPredictions />} />
        <Route path="/motion" element={<DemoMotion />} />
        <Route path="/about" element={<DemoAbout />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </DemoLayout>
  )
}
