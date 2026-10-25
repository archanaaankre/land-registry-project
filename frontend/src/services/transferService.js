import { ApiError, apiGet, apiPost } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

function descriptionForError(error, fallback) {
  if (error.status === 503 || error.code === 'registry_unavailable') {
    return 'The transfer registry is temporarily unavailable.'
  }
  return error?.message || fallback
}

function transferFromResponse(data, requestId) {
  const transfer = data?.transfer
  if (
    typeof transfer?.request_id !== 'string' ||
    !transfer.request_id.trim() ||
    typeof transfer.status !== 'string' ||
    !transfer.status.trim() ||
    (requestId && transfer.request_id !== requestId)
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return transfer
}

function transferItemsFromResponse(data) {
  if (
    !Array.isArray(data?.items) ||
    data.items.some(
      (transfer) =>
        typeof transfer?.request_id !== 'string' ||
        !transfer.request_id.trim() ||
        typeof transfer.status !== 'string' ||
        !transfer.status.trim(),
    )
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return data.items
}

async function transferRequest(path, options, fallbackFailureMessage) {
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
    throw new ApiError(descriptionForError(error, fallbackFailureMessage), error.status, error.code, error.field)
  }
}

export async function createTransfer(payload, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPost('/transfers', payload, { signal, token })
    return transferFromResponse(data)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw new ApiError(
      descriptionForError(error, 'Could not submit the transfer request.'),
      error.status,
      error.code,
      error.field,
    )
  }
}

export async function listTransfers({ signal } = {}) {
  const { data } = await transferRequest(
    '/transfers',
    { signal },
    'Could not load transfer requests.',
  )
  return transferItemsFromResponse(data)
}

export async function getTransfer(requestId, { signal } = {}) {
  const { data } = await transferRequest(
    `/transfers/${encodeURIComponent(requestId)}`,
    { signal },
    'Could not load transfer request details.',
  )
  const transfer = transferFromResponse(data, requestId)
  if (
    !Array.isArray(data.history) ||
    data.history.some(
      (event) => typeof event?.event_id !== 'string' || !event.event_id.trim(),
    )
  ) {
    throw new ApiError('We received an unexpected response. Please try again.')
  }
  return {
    transfer,
    history: data.history,
  }
}

export async function cancelTransfer(requestId, reason, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPost(
      `/transfers/${encodeURIComponent(requestId)}/cancel`,
      reason ? { reason } : undefined,
      { signal, token },
    )
    return transferFromResponse(data, requestId)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw new ApiError(descriptionForError(error, 'Could not cancel the transfer request.'), error.status, error.code, error.field)
  }
}

export async function listRegistrarTransfers({ signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiGet('/registrar/transfers', { signal, token })
    return transferItemsFromResponse(data)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw new ApiError(descriptionForError(error, 'Could not load the review queue.'), error.status, error.code, error.field)
  }
}

export async function approveTransfer(requestId, reason, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const body = reason ? { reason } : undefined
    const { data } = await apiPost(
      `/registrar/transfers/${encodeURIComponent(requestId)}/approve`,
      body,
      { signal, token },
    )
    return transferFromResponse(data, requestId)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw new ApiError(descriptionForError(error, 'Could not approve the transfer.'), error.status, error.code, error.field)
  }
}

export async function rejectTransfer(requestId, reason, { signal } = {}) {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  try {
    const { data } = await apiPost(
      `/registrar/transfers/${encodeURIComponent(requestId)}/reject`,
      { reason },
      { signal, token },
    )
    return transferFromResponse(data, requestId)
  } catch (error) {
    if (error.status === 401) {
      logoutUser()
    }
    throw new ApiError(descriptionForError(error, 'Could not reject the transfer.'), error.status, error.code, error.field)
  }
}

export function transferStatusLabel(status) {
  const labels = {
    DRAFT: 'Draft',
    SUBMITTED: 'Submitted — awaiting registrar review',
    UNDER_REVIEW: 'Registrar review in progress',
    APPROVED: 'Approved by registrar',
    BLOCKCHAIN_PENDING: 'Blockchain pending',
    COMPLETED: 'Completed',
    REJECTED: 'Rejected',
    FAILED: 'Failed',
    CANCELLED: 'Cancelled',
  }

  return labels[status] || status
}

export function blockchainStatusLabel(status) {
  const labels = {
    NOT_SUBMITTED: 'Not submitted',
    PENDING: 'Pending',
    SUBMITTED: 'Submitted',
    CONFIRMED: 'Confirmed',
    FAILED: 'Failed',
    UNAVAILABLE: 'Unavailable',
  }

  return status ? labels[status] || status : 'Not available'
}