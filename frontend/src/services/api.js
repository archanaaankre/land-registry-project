const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export class ApiError extends Error {
  constructor(message, status = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function apiGet(path, { signal } = {}) {
  if (!API_BASE_URL) {
    throw new ApiError('VITE_API_BASE_URL is not configured.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
  let response

  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
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

  let body
  try {
    body = await response.json()
  } catch {
    throw new ApiError('The backend returned invalid JSON.', response.status)
  }

  if (!response.ok) {
    throw new ApiError(
      body?.error?.message || `The backend request failed with status ${response.status}.`,
      response.status,
    )
  }

  return { data: body, status: response.status }
}
