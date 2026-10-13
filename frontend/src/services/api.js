const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export class ApiError extends Error {
  constructor(message, status = null, code = null, field = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.field = field
  }
}

async function apiRequest(path, { method = 'GET', body, signal, token } = {}) {
  if (!API_BASE_URL) {
    throw new ApiError('VITE_API_BASE_URL is not configured.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
  const headers = { Accept: 'application/json' }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('Could not reach the backend. Check that Flask is running.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'The backend returned an unexpected response.'
        : `The backend request failed with status ${response.status}.`,
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('The backend returned invalid JSON.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || `The backend request failed with status ${response.status}.`,
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export function apiGet(path, options = {}) {
  return apiRequest(path, options)
}

export function apiPost(path, body, options = {}) {
  return apiRequest(path, { ...options, method: 'POST', body })
}
