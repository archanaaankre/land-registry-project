import { ApiError, apiGet } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

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
  if (!Array.isArray(data?.items)) {
    throw new ApiError('The backend returned an invalid parcel list.')
  }
  return data.items
}

export async function getParcel(parcelId, { signal } = {}) {
  const { data } = await parcelRequest(
    `/parcels/${encodeURIComponent(parcelId)}`,
    { signal },
  )
  if (!data?.parcel || typeof data.parcel.parcel_id !== 'string') {
    throw new ApiError('The backend returned invalid parcel details.')
  }
  return data.parcel
}

export async function getParcelOwnership(parcelId, { signal } = {}) {
  const { data } = await parcelRequest(
    `/parcels/${encodeURIComponent(parcelId)}/ownership`,
    { signal },
  )
  if (!Array.isArray(data?.items)) {
    throw new ApiError('The backend returned an invalid ownership list.')
  }
  return data.items
}
