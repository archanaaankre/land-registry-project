import { ApiError, apiGet, apiPost } from './api.js'

const TOKEN_STORAGE_KEY = 'land-registry-access-token'

export function getAccessToken() {
  return window.sessionStorage.getItem(TOKEN_STORAGE_KEY)
}

function storeAccessToken(response) {
  if (
    typeof response?.access_token !== 'string' ||
    !response.access_token ||
    typeof response.token_type !== 'string' ||
    response.token_type.toLowerCase() !== 'bearer' ||
    !response.user ||
    typeof response.user.id !== 'string' ||
    !['CITIZEN', 'REGISTRAR', 'ADMIN'].includes(response.user.role)
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }

  window.sessionStorage.setItem(TOKEN_STORAGE_KEY, response.access_token)
  return response.user
}

export async function registerUser({ name, email, password }) {
  const { data } = await apiPost('/auth/register', {
    name,
    email,
    password,
    role: 'CITIZEN',
  })
  return storeAccessToken(data)
}

export async function loginUser({ email, password }) {
  const { data } = await apiPost('/auth/login', { email, password })
  return storeAccessToken(data)
}

export async function getCurrentUser() {
  const token = getAccessToken()
  if (!token) {
    return null
  }

  try {
    const { data } = await apiGet('/auth/me', { token })
    const user = data?.user
    if (
      typeof user?.id !== 'string' ||
      !['CITIZEN', 'REGISTRAR', 'ADMIN'].includes(user.role)
    ) {
      throw new ApiError('We received an unexpected response. Please try again.')
    }
    return user
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export function logoutUser() {
  window.sessionStorage.removeItem(TOKEN_STORAGE_KEY)
}
