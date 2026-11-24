import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { Layout } from './components/Layout'
import { Audit } from './pages/Audit'
import { Customers } from './pages/Customers'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { Monitoring } from './pages/Monitoring'
import { Reviews } from './pages/Reviews'
import { Transactions } from './pages/Transactions'

// recharts is heavy: only load it when an analyst opens these pages
const Model = lazy(() => import('./pages/Model').then((m) => ({ default: m.Model })))
const Visualizations = lazy(() => import('./pages/Visualizations').then((m) => ({ default: m.Visualizations })))

const STAFF = ['ADMIN', 'ANALYST'] as const

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Dashboard />} />
        <Route path="transactions" element={<Transactions />} />
        <Route path="customers" element={<Customers />} />
        <Route path="reviews" element={<ProtectedRoute roles={[...STAFF]}><Reviews /></ProtectedRoute>} />
        <Route path="audit" element={<ProtectedRoute roles={[...STAFF]}><Audit /></ProtectedRoute>} />
        <Route path="model" element={<ProtectedRoute roles={[...STAFF]}><Suspense fallback={<p className="muted">Loading...</p>}><Model /></Suspense></ProtectedRoute>} />
        <Route path="visualizations" element={<ProtectedRoute roles={[...STAFF]}><Suspense fallback={<p className="muted">Loading...</p>}><Visualizations /></Suspense></ProtectedRoute>} />
        <Route path="monitoring" element={<ProtectedRoute roles={[...STAFF]}><Monitoring /></ProtectedRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
