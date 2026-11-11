import { lazy, Suspense } from 'react'
import App from './App.tsx'

// /admin: the form for adding knowledge (loaded only there, so the chat stays small).
const AdminPage = lazy(() => import('./admin/AdminPage.tsx'))

/**
 * Picks the page from the address: /admin -> the form, anything else -> the chat.
 * Called by: main.tsx
 */
export default function Root() {
  const isAdmin = window.location.pathname.replace(/\/+$/, '') === '/admin'
  return isAdmin ? <Suspense fallback={null}><AdminPage /></Suspense> : <App />
}
