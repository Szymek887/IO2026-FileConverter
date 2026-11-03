import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

async function bootstrap() {
  // `npm run dev:mock` (vite --mode mock) answers /api with an in-browser mock of the backend.
  if (import.meta.env.VITE_API_MOCK === 'true') {
    const { startMockApi } = await import('./mocks/browser')
    await startMockApi()
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void bootstrap()
