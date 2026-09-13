/// <reference types="vite/client" />

/**
 * UV printing development switches.
 *
 * Both default to "off" when undefined. `VITE_UV_PREVIEW` may only register the
 * sample transport in a DEV build; `VITE_UV_ENABLED` is the future release gate
 * that the backend permission registration owns.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_UV_PREVIEW?: string
  readonly VITE_UV_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
