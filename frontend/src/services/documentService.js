import { ApiError } from './api.js'
import { getAccessToken } from './authService.js'

export async function storeDocumentHash(formData, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const headers = { Accept: 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/hash`

  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function uploadSupportingDocument(
  formData,
  { signal, parcelId, transferRequestId, contentType } = {},
) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  if (parcelId !== undefined && formData) {
    formData.append('parcel_id', parcelId)
  }
  if (transferRequestId !== undefined && formData) {
    formData.append('transfer_request_id', transferRequestId)
  }
  if (contentType !== undefined && formData) {
    formData.append('content_type', contentType)
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/upload`
  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
      body: formData,
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const responseContentType = response.headers.get('content-type') || ''
  if (!responseContentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function verifyDocument(documentId, formData, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const headers = { Accept: 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(documentId)}/verify`

  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function listDocumentHashes({ signal, parcelId } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  let url = `${API_BASE_URL.replace(/\/+$/, '')}/documents`
  if (parcelId) {
    url += `?parcel_id=${encodeURIComponent(parcelId)}`
  }

  let response
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function getDocumentHash(documentId, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(documentId)}`

  let response
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function listSupportingDocuments({ signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/supporting`

  let response
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function getSupportingDocument(documentId, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/supporting/${encodeURIComponent(documentId)}`

  let response
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      response.ok
        ? 'We received an unexpected response. Please try again.'
        : 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  let responseBody
  try {
    responseBody = await response.json()
  } catch {
    throw new ApiError('We received an unexpected response. Please try again.', response.status)
  }

  if (!response.ok) {
    const error = responseBody?.error
    throw new ApiError(
      error?.message || 'This request could not be completed. Please try again.',
      response.status,
      error?.code || null,
      error?.field || null,
    )
  }

  return { data: responseBody, status: response.status }
}

export async function downloadSupportingDocument(documentId, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  if (!API_BASE_URL) {
    throw new ApiError('This request could not be completed. Please try again later.')
  }

  const url = `${API_BASE_URL.replace(/\/+$/, '')}/documents/supporting/${encodeURIComponent(documentId)}/download`

  let response
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/octet-stream',
        Authorization: `Bearer ${token}`,
      },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError('This request could not be completed. Please try again.')
  }

  if (!response.ok) {
    throw new ApiError(
      response.statusText || 'This request could not be completed. Please try again.',
      response.status,
    )
  }

  const data = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  const filename = (match && match[1]) || `${documentId}.bin`

  return {
    data,
    filename,
    contentType: response.headers.get('content-type'),
    status: response.status,
  }
}
