import { ApiError, apiGet, apiPatch, apiPost } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

function requireUser(user) {
  if (
    typeof user?.id !== 'string' ||
    typeof user.name !== 'string' ||
    typeof user.email !== 'string' ||
    typeof user.role !== 'string' ||
    typeof user.is_active !== 'boolean'
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return user
}

async function adminRequest(request) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError(
      'Your session has expired. Sign in again.',
      401,
      'missing_authentication',
    )
  }

  try {
    return await request(token)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function listAdminUsers({ role, isActive, signal } = {}) {
  const params = new URLSearchParams()
  if (role) params.set('role', role)
  if (isActive !== undefined && isActive !== null && isActive !== '') {
    params.set('is_active', isActive)
  }
  const query = params.size ? `?${params.toString()}` : ''

  const { data } = await adminRequest((token) =>
    apiGet(`/admin/users${query}`, { signal, token }),
  )
  const items = data?.users ?? data?.items
  if (!Array.isArray(items)) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return items.map(requireUser)
}

export async function createAdminUser(payload) {
  const { data } = await adminRequest((token) =>
    apiPost('/admin/users', payload, { token }),
  )
  return requireUser(data?.user)
}

export async function updateAdminUserRole(userId, role) {
  const { data } = await adminRequest((token) =>
    apiPatch(`/admin/users/${encodeURIComponent(userId)}/role`, { role }, { token }),
  )
  return requireUser(data?.user)
}

export async function updateAdminUserStatus(userId, isActive) {
  const { data } = await adminRequest((token) =>
    apiPatch(
      `/admin/users/${encodeURIComponent(userId)}/status`,
      { is_active: isActive },
      { token },
    ),
  )
  return requireUser(data?.user)
}
