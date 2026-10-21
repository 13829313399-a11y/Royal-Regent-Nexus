/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_CUTTING_ACCEPTANCE_RELEASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
