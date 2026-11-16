import { ApiError, apiGet, apiPost, apiPatch } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

export async function listAdminUsers({ signal, search, role, isActive } = {}) {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  if (role) params.set('role', role)
  if (isActive !== undefined) params.set('is_active', String(isActive))

  const path = params.toString() ? `/api/admin/users?${params.toString()}` : '/api/admin/users'

  try {
    const { data } = await apiGet(path, { signal, token: getAccessToken() })
    return data.users ?? []
  } catch (error) {
    if (error.name === 'AbortError') throw error
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function createAdminUser(payload, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPost('/api/admin/users', payload, { signal, token })
    return data
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function updateAdminUserRole(userId, role, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPatch(
      `/api/admin/users/${encodeURIComponent(userId)}/role`,
      { role },
      { signal, token }
    )
    return data.user
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function updateAdminUserStatus(userId, isActive, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPatch(
      `/api/admin/users/${encodeURIComponent(userId)}/status`,
      { is_active: isActive },
      { signal, token }
    )
    return data.user
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function getAdminStats({ signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiGet('/api/admin/stats', { signal, token })
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw error
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}
