/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CUTTING_ACCEPTANCE_RELEASE?: string
  readonly VITE_CUTTING_PO_TEST_BRIDGE?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_IAM_IDENTITY_UI_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
