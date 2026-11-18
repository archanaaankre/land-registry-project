import { ApiError, apiPost } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

function descriptionForError(error, fallback) {
  if (error.status === 503 || error.code === 'registry_unavailable') {
    return 'The ownership registry is temporarily unavailable.'
  }
  // 4xx messages come from the API and are safe to show (400 invalid_input
  // with field, 404 parcel/owner not found, 409 share/duplicate conflicts).
  return error?.message || fallback
}

function ownershipFromResponse(data) {
  const ownership = data?.ownership
  if (
    typeof ownership?.ownership_id !== 'string' ||
    !ownership.ownership_id.trim() ||
    typeof ownership?.parcel_id !== 'string' ||
    !ownership.parcel_id.trim() ||
    typeof ownership?.owner_id !== 'string' ||
    !ownership.owner_id.trim() ||
    typeof ownership?.share !== 'string' ||
    typeof ownership?.status !== 'string'
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return {
    ownership_id: ownership.ownership_id,
    parcel_id: ownership.parcel_id,
    owner_id: ownership.owner_id,
    share: ownership.share,
    status: ownership.status,
    created_at: ownership.created_at ?? null,
    updated_at: ownership.updated_at ?? null,
  }
}

export async function createOwnership(payload, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPost('/ownership', payload, { signal, token })
    return ownershipFromResponse(data)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    if (error?.name === 'AbortError') {
      throw error
    }
    throw new ApiError(
      descriptionForError(error, 'Ownership could not be recorded. Please try again.'),
      error.status,
      error.code,
      error.field,
    )
  }
}
