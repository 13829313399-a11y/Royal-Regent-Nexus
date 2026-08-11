import 'axios'

declare module 'axios' {
  interface AxiosRequestConfig<D = any> {
    /**
     * Use only when a 403 is an expected, endpoint-specific capability denial.
     * It never suppresses the global 401 session-expiry handler.
     */
    skipForbiddenSessionRefresh?: boolean
  }

  interface InternalAxiosRequestConfig<D = any> {
    skipForbiddenSessionRefresh?: boolean
  }
}
