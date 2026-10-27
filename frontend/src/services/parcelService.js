import { ApiError, apiGet, apiPost } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

function itemsFromResponse(data, identifier) {
  if (
    !Array.isArray(data?.items) ||
    data.items.some(
      (item) =>
        typeof item?.[identifier] !== 'string' ||
        !item[identifier].trim(),
    )
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return data.items
}

async function parcelRequest(path, options) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    return await apiGet(path, { ...options, token })
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function listParcels({ signal } = {}) {
  const { data } = await parcelRequest('/parcels', { signal })
  return itemsFromResponse(data, 'parcel_id')
}

export async function createParcel(payload, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPost('/parcels', payload, { signal, token })
    if (typeof data?.parcel?.parcel_id !== 'string' || !data.parcel.parcel_id.trim()) {
      throw new ApiError('We received an unexpected response. Please try again.')
    }
    return data.parcel
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw error
  }
}

export async function getParcel(parcelId, { signal } = {}) {
  const { data } = await parcelRequest(
    `/parcels/${encodeURIComponent(parcelId)}`,
    { signal },
  )
  if (!data?.parcel || typeof data.parcel.parcel_id !== 'string') {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return data.parcel
}

export async function getParcelOwnership(parcelId, { signal } = {}) {
  const { data } = await parcelRequest(
    `/parcels/${encodeURIComponent(parcelId)}/ownership`,
    { signal },
  )
  return itemsFromResponse(data, 'ownership_id')
}
