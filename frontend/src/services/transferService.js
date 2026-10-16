import { ApiError, apiGet, apiPost } from './api.js'
import { getAccessToken, logoutUser } from './authService.js'

function descriptionForError(error, fallback) {
  if (error.status === 503 || error.code === 'registry_unavailable') {
    return 'The transfer registry is temporarily unavailable.'
  }
  return error?.message || fallback
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
    if (!data?.transfer) {
      throw new ApiError('The backend returned an invalid transfer response.')
    }
    return data.transfer
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
  if (!Array.isArray(data?.items)) {
    throw new ApiError('The backend returned an invalid transfer list.')
  }
  return data.items
}

export async function getTransfer(requestId, { signal } = {}) {
  const { data } = await transferRequest(
    `/transfers/${encodeURIComponent(requestId)}`,
    { signal },
    'Could not load transfer request details.',
  )
  if (!data?.transfer) {
    throw new ApiError('The backend returned invalid transfer details.')
  }
  return {
    transfer: data.transfer,
    history: Array.isArray(data.history) ? data.history : [],
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
    if (!data?.transfer) {
      throw new ApiError('The backend returned an invalid transfer response.')
    }
    return data.transfer
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
    if (!Array.isArray(data?.items)) {
      throw new ApiError('The backend returned an invalid review queue.')
    }
    return data.items
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
    if (!data?.transfer) {
      throw new ApiError('The backend returned an invalid transfer response.')
    }
    return data.transfer
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
    if (!data?.transfer) {
      throw new ApiError('The backend returned an invalid transfer response.')
    }
    return data.transfer
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
    SUBMITTED: 'Submitted',
    UNDER_REVIEW: 'Under review',
    APPROVED: 'Approved (blockchain not started)',
    BLOCKCHAIN_PENDING: 'Blockchain pending',
    COMPLETED: 'Completed',
    REJECTED: 'Rejected',
    FAILED: 'Failed',
    CANCELLED: 'Cancelled',
  }

  return labels[status] || status
}