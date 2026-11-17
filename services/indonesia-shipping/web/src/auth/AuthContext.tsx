import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import { nexusBase, nexusBusinessUrl } from '../deployment'
import { getStoredSession, hasBits, isAdminSession, saveSession, subscribeSession, type AuthSession, type ModuleKey, PERMISSION_MODULES } from './permissions'
import { installNexusSessionSync } from './nexusSessionSync'
import { confirmNavigation } from './navigationState'

interface AuthContextValue {
  session: AuthSession | null
  loading: boolean
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  canAccess: (key: ModuleKey) => boolean
  canEdit: (key: ModuleKey) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(() => getStoredSession())
  const [loading, setLoading] = useState(!!nexusBase() || !!getStoredSession())

  useEffect(() => {
    if (nexusBase()) {
      const unsubscribe = subscribeSession(setSession)
      const stop = installNexusSessionSync(async () => (await api.get<AuthSession>('/session', { skipErrorToast: true, timeout: 15000 } as any)).data,
        () => setLoading(false))
      return () => { stop(); unsubscribe(); saveSession(null) }
    }
    const stored = getStoredSession()
    if (!stored?.token) { setLoading(false); return }
    api.get('/users/me').then(({ data }) => {
      const next = { ...stored, displayName: data.displayName, userbqrpower: data.userbqrpower, usereditpower: data.usereditpower }
      setSession(next); saveSession(next)
    }).catch(() => { setSession(null); saveSession(null) }).finally(() => setLoading(false))
  }, [])

  async function login(username: string, password: string) {
    if (nexusBase()) throw new Error('请使用 Nexus 账号入口')
    const { data } = await api.post<AuthSession>('/auth/login', { username, password })
    const next = { token: data.token, displayName: data.displayName, userbqrpower: data.userbqrpower, usereditpower: data.usereditpower }
    saveSession(next); setSession(next)
  }

  async function logout() {
    if (nexusBase() && !await confirmNavigation()) return
    saveSession(null); setSession(null)
    if (nexusBase()) window.top!.location.href = nexusBusinessUrl()
  }
  const value = useMemo<AuthContextValue>(() => ({
    session, loading, isAdmin: isAdminSession(session), login, logout,
    canAccess: (key) => {
      const mod = PERMISSION_MODULES.find(x => x.key === key)
      return !!mod && hasBits(session?.userbqrpower, mod.positions)
    },
    canEdit: (key) => {
      const mod = PERMISSION_MODULES.find(x => x.key === key)
      return !!mod && hasBits(session?.usereditpower, mod.positions)
    },
  }), [session, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const v = useContext(AuthContext)
  if (!v) throw new Error('useAuth must be used inside AuthProvider')
  return v
}
