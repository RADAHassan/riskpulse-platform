import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { login as apiLogin, logout as apiLogout, restoreSession, session } from '../api/client'
import type { Role, TokenResponse } from '../api/types'

interface AuthState {
  user: TokenResponse | null
  /** true while the stored refresh token is being exchanged after a page reload */
  restoring: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<TokenResponse | null>(session.user)
  const [restoring, setRestoring] = useState<boolean>(!session.user && session.refreshToken !== null)

  useEffect(() => {
    const unsubscribe = session.subscribe(setUser)
    if (restoring) {
      void restoreSession().finally(() => setRestoring(false))
    }
    return unsubscribe
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password)
  }, [])
  const logout = useCallback(async () => {
    await apiLogout()
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      restoring,
      login,
      logout,
      hasRole: (...roles: Role[]) => user !== null && roles.includes(user.role),
    }),
    [user, restoring, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
