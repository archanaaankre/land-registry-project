import { useEffect, useMemo, useState } from 'react'
import { AuthContext } from './authContext.js'
import {
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from '../services/authService.js'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [status, setStatus] = useState('loading')
  const [sessionError, setSessionError] = useState('')

  useEffect(() => {
    let active = true
    getCurrentUser()
      .then((currentUser) => {
        if (active) {
          setUser(currentUser)
          setStatus(currentUser ? 'authenticated' : 'unauthenticated')
        }
      })
      .catch((error) => {
        if (active) {
          setUser(null)
          setStatus(error.status === 401 ? 'unauthenticated' : 'error')
          setSessionError(error.message)
        }
      })

    return () => {
      active = false
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      status,
      sessionError,
      async login(credentials) {
        const authenticatedUser = await loginUser(credentials)
        setUser(authenticatedUser)
        setSessionError('')
        setStatus('authenticated')
        return authenticatedUser
      },
      async register(details) {
        const authenticatedUser = await registerUser(details)
        setUser(authenticatedUser)
        setSessionError('')
        setStatus('authenticated')
        return authenticatedUser
      },
      logout() {
        logoutUser()
        setUser(null)
        setSessionError('')
        setStatus('unauthenticated')
      },
      async retrySessionCheck() {
        setStatus('loading')
        setSessionError('')
        try {
          const currentUser = await getCurrentUser()
          setUser(currentUser)
          setStatus(currentUser ? 'authenticated' : 'unauthenticated')
        } catch (error) {
          setUser(null)
          setStatus(error.status === 401 ? 'unauthenticated' : 'error')
          setSessionError(error.message)
        }
      },
    }),
    [user, status, sessionError],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
