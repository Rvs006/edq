import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authApi } from '@/lib/api'

interface User {
  id: string
  email: string
  username: string
  full_name: string | null
  role: 'engineer' | 'reviewer' | 'admin'
  is_active: boolean
}

interface AuthContextType {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// TODO: Remove DEV_BYPASS_AUTH before production
const DEV_BYPASS_AUTH = true
const MOCK_USER: User = {
  id: 'dev-mock-id',
  email: 'admin@electracom.co.uk',
  username: 'admin',
  full_name: 'Admin User',
  role: 'admin',
  is_active: true,
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(DEV_BYPASS_AUTH ? MOCK_USER : null)
  const [loading, setLoading] = useState(DEV_BYPASS_AUTH ? false : true)

  const fetchUser = useCallback(async () => {
    if (DEV_BYPASS_AUTH) { setUser(MOCK_USER); setLoading(false); return }
    try {
      const { data } = await authApi.me()
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUser()
  }, [fetchUser])

  const login = async (username: string, password: string) => {
    if (DEV_BYPASS_AUTH) { setUser(MOCK_USER); return }
    await authApi.login({ username, password })
    await fetchUser()
  }

  const logout = async () => {
    if (DEV_BYPASS_AUTH) { return }
    try {
      await authApi.logout()
    } catch {
      // ignore
    }
    setUser(null)
  }

  const refreshUser = async () => {
    await fetchUser()
  }

  return (
    <AuthContext.Provider value={{ user, loading, isAuthenticated: !!user, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
