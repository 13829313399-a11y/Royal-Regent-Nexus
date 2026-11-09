import '@/lib/initBuffer.js'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './codex.css'
import ErrorBoundary from './components/ErrorBoundary.tsx'
import CodexWorkbench from './pages/CodexWorkbench.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <CodexWorkbench />
    </ErrorBoundary>
  </StrictMode>,
)
