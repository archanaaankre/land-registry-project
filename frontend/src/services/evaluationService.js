import { ApiError, apiGet } from './api.js'
import { listDocumentHashes } from './documentService.js'
import { listParcels, getParcelOwnership } from './parcelService.js'

const MEASUREMENT_SAMPLE_SIZE = 5
const PERFORMANCE_ENDPOINTS = [
  {
    key: 'auth-me',
    label: 'Current-user API',
    path: '/auth/me',
    requiresAuthentication: true,
  },
  {
    key: 'parcels',
    label: 'Parcel list API',
    path: '/parcels',
    requiresAuthentication: true,
  },
]

function createUnavailableMetric(reason, details = {}) {
  return {
    status: 'unavailable',
    reason,
    ...details,
  }
}

function normalizeNumber(value) {
  return Number.isFinite(value) ? value : null
}

function roundMilliseconds(value) {
  return Math.round(value * 10) / 10
}

function parseTimestamp(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function sortEventsChronologically(events) {
  return [...events].sort((first, second) => {
    const firstTime = parseTimestamp(first.timestamp)?.getTime() ?? Number.POSITIVE_INFINITY
    const secondTime = parseTimestamp(second.timestamp)?.getTime() ?? Number.POSITIVE_INFINITY
    return firstTime - secondTime
  })
}

export async function getDocumentIntegritySummary({ token, signal } = {}) {
  if (!token) {
    return createUnavailableMetric('missing_authentication', {
      title: 'Document integrity',
      message: 'Authentication is required to verify document integrity.',
      disclaimer:
        'A matching cryptographic hash establishes content consistency with a recorded hash. It does not establish the document’s legal authenticity.',
    })
  }

  try {
    const { data } = await listDocumentHashes({ signal })
    const documents = data.documents ?? []

    let matched = 0
    let mismatched = 0
    let notVerified = 0

    for (const doc of documents) {
      if (doc.last_verification_status === 'MATCHED') {
        matched += 1
      } else if (doc.last_verification_status === 'MISMATCHED') {
        mismatched += 1
      } else {
        notVerified += 1
      }
    }

    return {
      status: 'loaded',
      title: 'Document integrity',
      totalDocuments: documents.length,
      matched,
      mismatched,
      notVerified,
      disclaimer:
        'A matching cryptographic hash establishes content consistency with a recorded hash. It does not establish the document’s legal authenticity.',
    }
  } catch (error) {
    if (error?.name === 'AbortError' || signal?.aborted) {
      throw error
    }
    return createUnavailableMetric(error?.code || 'verification_failed', {
      title: 'Document integrity',
      message:
        error?.message ||
        'Document integrity verification is temporarily unavailable.',
      disclaimer:
        'A matching cryptographic hash establishes content consistency with a recorded hash. It does not establish the document’s legal authenticity.',
    })
  }
}

export async function getTamperDetectionSummary({ token, signal } = {}) {
  if (!token) {
    return createUnavailableMetric('missing_authentication', {
      title: 'Tamper detection',
      message: 'Authentication is required for tamper detection.',
      formula:
        'Detection rate = correctly detected tampering attempts / total tampering attempts tested x 100',
      denominatorRule: 'Only tampering attempts belong in the denominator; original-record integrity checks are reported separately.',
    })
  }

  try {
    const { data } = await listDocumentHashes({ signal })
    const documents = data.documents ?? []

    let matched = 0
    let mismatched = 0
    let notVerified = 0

    for (const doc of documents) {
      if (doc.last_verification_status === 'MATCHED') {
        matched += 1
      } else if (doc.last_verification_status === 'MISMATCHED') {
        mismatched += 1
      } else {
        notVerified += 1
      }
    }

    const totalTested = matched + mismatched
    const detectionRate =
      totalTested > 0 ? (mismatched / totalTested) * 100 : null

    return {
      status: 'loaded',
      title: 'Tamper detection',
      totalDocuments: documents.length,
      verified: matched,
      modified: mismatched,
      notVerified,
      totalTested,
      detectionRate: detectionRate !== null ? Math.round(detectionRate * 10) / 10 : null,
      formula:
        'Detection rate = modified documents detected / total documents tested x 100',
      denominatorRule:
        'Only documents that have been verified belong in the denominator; documents never verified are reported separately.',
    }
  } catch (error) {
    if (error?.name === 'AbortError' || signal?.aborted) {
      throw error
    }
    return createUnavailableMetric(error?.code || 'detection_failed', {
      title: 'Tamper detection',
      message:
        error?.message ||
        'Tamper detection is temporarily unavailable.',
      formula:
        'Detection rate = correctly detected tampering attempts / total tampering attempts tested x 100',
      denominatorRule: 'Only tampering attempts belong in the denominator; original-record integrity checks are reported separately.',
    })
  }
}

export const ACCESS_CONTROL_POLICY = {
  source: 'Backend authorization constants and protected routes (app/registry/authorization.py, app/auth/decorators.py).',
  roles: ['CITIZEN', 'REGISTRAR', 'ADMIN', 'VERIFICATION_OFFICER'],
  actions: [
    {
      key: 'view-parcels',
      label: 'View parcels and parcel details',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'VERIFICATION_OFFICER', 'ADMIN'],
      notes: 'GET /api/parcels and GET /api/parcels/:parcelId use PARCEL_READ_ROLES, which includes VERIFICATION_OFFICER.',
    },
    {
      key: 'view-ownership',
      label: 'View ownership records for a parcel',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'VERIFICATION_OFFICER', 'ADMIN'],
      notes: 'GET /api/parcels/:parcelId/ownership uses OWNERSHIP_READ_ROLES, which includes VERIFICATION_OFFICER.',
    },
    {
      key: 'view-transfers',
      label: 'View transfer requests and audit history',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'VERIFICATION_OFFICER', 'ADMIN'],
      notes: 'GET /api/transfers and GET /api/transfers/:requestId use TRANSFER_READ_ROLES. Citizens only see requests where they are the seller or buyer; Verification Officers may view all requests but cannot approve or reject.',
    },
    {
      key: 'upload-supporting-document',
      label: 'Upload supporting documents (no trusted baseline)',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'VERIFICATION_OFFICER'],
      notes: 'POST /api/documents/upload returns a calculated SHA-256 hash but stores nothing. Administrators cannot upload supporting documents.',
    },
    {
      key: 'create-trusted-hash',
      label: 'Create/store trusted document hashes',
      allowedRoles: ['REGISTRAR'],
      notes: 'POST /api/documents/hash is Registrar-only. Verification Officers, Citizens and Administrators cannot establish trusted baselines.',
    },
    {
      key: 'verify-documents',
      label: 'Verify documents against stored SHA-256 hashes',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'VERIFICATION_OFFICER', 'ADMIN'],
      notes: 'POST /api/documents/:documentId/verify. Verification Officers and Administrators may verify any stored document; citizens may only verify documents they uploaded or that relate to parcels they actively own.',
    },
    {
      key: 'manage-parcels',
      label: 'Manage (create/update) parcel records',
      allowedRoles: ['REGISTRAR'],
      notes: 'PARCEL_MANAGE_ROLES contains only REGISTRAR. No public write endpoint is currently exposed.',
    },
    {
      key: 'record-ownership',
      label: 'Record ownership changes or transfers',
      allowedRoles: ['REGISTRAR'],
      notes: 'OWNERSHIP_RECORD_ROLES contains only REGISTRAR. No public write endpoint is currently exposed.',
    },
    {
      key: 'submit-transfer',
      label: 'Submit a transfer request',
      allowedRoles: ['CITIZEN'],
      notes: 'POST /api/transfers uses TRANSFER_SUBMIT_ROLES.',
    },
    {
      key: 'review-transfer',
      label: 'Approve or reject a transfer request',
      allowedRoles: ['REGISTRAR'],
      notes: 'Registrar transfer decisions use TRANSFER_REVIEW_ROLES.',
    },
  ],
  measuredResults: null,
}

export function getAccessControlSummary() {
  return {
    status: 'policy_only',
    policy: ACCESS_CONTROL_POLICY,
    message:
      'The matrix below reflects configured authorization rules. No RBAC test result dataset or unauthorized-attempt report is available.',
    countsAvailable: false,
  }
}

export async function getOwnershipTraceability({ token, signal }) {
  if (!token) {
    throw new ApiError('Your session has expired. Sign in again.', 401, 'missing_authentication')
  }

  let parcels
  const errors = []

  try {
    parcels = await listParcels({ signal })
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw error
    }
    if (error?.status === 401) {
      throw error
    }
    return {
      status: 'unavailable',
      source: 'GET /api/parcels',
      parcels: [],
      events: [],
      errors: ['We could not load ownership records. Please try again.'],
      message:
        'Ownership records could not be loaded. Please try again later.',
    }
  }

  const ownershipResults = await Promise.allSettled(
    parcels.map(async (parcel) => {
      const records = await getParcelOwnership(parcel.parcel_id, { signal })
      return { parcel, records }
    }),
  )

  const events = []
  for (const result of ownershipResults) {
    if (result.status === 'rejected') {
      if (result.reason?.name === 'AbortError') {
        throw result.reason
      }
      if (result.reason?.status === 401) {
        throw result.reason
      }
      errors.push(describeBackendError(result.reason, 'ownership records'))
      continue
    }

    const { parcel, records } = result.value
    const orderedRecords = [...records].sort((first, second) => {
      const firstTime = parseTimestamp(first.created_at)?.getTime() ?? Number.POSITIVE_INFINITY
      const secondTime = parseTimestamp(second.created_at)?.getTime() ?? Number.POSITIVE_INFINITY
      return firstTime - secondTime
    })

    for (const record of orderedRecords) {
      events.push({
        id: `${parcel.parcel_id}-${record.ownership_id}-${record.created_at}`,
        parcelId: parcel.parcel_id,
        cadastralNumber: parcel.cadastral_number,
        ownershipRecordId: record.ownership_id,
        ownerReference: record.owner_id,
        eventType: 'Recorded ownership row',
        timestamp: record.created_at,
        recordStatus: record.status,
        share: record.share,
        transactionId: null,
        blockchainConfirmation: 'not_available',
      })
    }
  }

  return {
    status: errors.length === 0 ? 'loaded' : 'partial',
    source: 'GET /api/parcels and GET /api/parcels/:parcelId/ownership',
    parcels,
    events: sortEventsChronologically(events),
    errors,
    message:
      parcels.length === 0
        ? 'No ownership records are available yet.'
        : 'Entries come from parcel ownership records. They do not represent transfer events or blockchain confirmations.',
  }
}

function describeBackendError(error, subject) {
  if (error?.status === 503 || error?.code === 'registry_unavailable') {
    return `We could not complete the ${subject} request. Please try again.`
  }
  return `We could not complete the ${subject} request. Please try again.`
}

export async function measureApiPerformance({ token, signal }) {
  const endpointResults = []

  for (const endpoint of PERFORMANCE_ENDPOINTS) {
    if (endpoint.requiresAuthentication && !token) {
      endpointResults.push({
        ...endpoint,
        status: 'unavailable',
        sampleSize: 0,
        successfulRequests: 0,
        failedRequests: 0,
        averageResponseTimeMs: null,
        minimumResponseTimeMs: null,
        maximumResponseTimeMs: null,
        requests: [],
        error: 'Authentication is required for this endpoint.',
      })
      continue
    }

    const requests = []
    let successfulRequests = 0
    let failedRequests = 0
    let totalLatency = 0
    let minimumResponseTimeMs = null
    let maximumResponseTimeMs = null

    for (let index = 0; index < MEASUREMENT_SAMPLE_SIZE; index += 1) {
      if (signal?.aborted) {
        throw new DOMException('Aborted', 'AbortError')
      }

      const requestSignal = signal
      const startedAt = globalThis.performance.now()
      let latency
      let requestError = null

      try {
        await apiGet(endpoint.path, {
          signal: requestSignal,
          token: endpoint.requiresAuthentication ? token : undefined,
        })
        successfulRequests += 1
      } catch (error) {
        if (error?.name === 'AbortError' || signal?.aborted) {
          throw error?.name === 'AbortError' ? error : new DOMException('Aborted', 'AbortError')
        }
        if (error?.status === 401) {
          throw error
        }
        failedRequests += 1
        requestError = describeBackendError(error, endpoint.label)
      }

      latency = roundMilliseconds(globalThis.performance.now() - startedAt)
      requests.push({
        index: index + 1,
        latencyMs: latency,
        success: requestError === null,
        error: requestError,
      })

      totalLatency += latency
      minimumResponseTimeMs =
        minimumResponseTimeMs === null ? latency : Math.min(minimumResponseTimeMs, latency)
      maximumResponseTimeMs =
        maximumResponseTimeMs === null ? latency : Math.max(maximumResponseTimeMs, latency)
    }

    endpointResults.push({
      ...endpoint,
      status: failedRequests === MEASUREMENT_SAMPLE_SIZE ? 'unavailable' : 'measured',
      sampleSize: MEASUREMENT_SAMPLE_SIZE,
      successfulRequests,
      failedRequests,
      averageResponseTimeMs:
        successfulRequests > 0 || failedRequests > 0
          ? roundMilliseconds(totalLatency / MEASUREMENT_SAMPLE_SIZE)
          : null,
      minimumResponseTimeMs,
      maximumResponseTimeMs,
      requests,
      error: failedRequests > 0 ? 'One or more sample requests failed; see sample details.' : null,
    })
  }

  const totalRequests = endpointResults.reduce((total, endpoint) => total + endpoint.sampleSize, 0)
  const successfulRequests = endpointResults.reduce((total, endpoint) => total + endpoint.successfulRequests, 0)
  const failedRequests = endpointResults.reduce((total, endpoint) => total + endpoint.failedRequests, 0)
  const weightedLatencyNumerator = endpointResults.reduce(
    (total, endpoint) => total + (endpoint.averageResponseTimeMs ?? 0) * endpoint.sampleSize,
    0,
  )
  const weightedAverageResponseTimeMs =
    totalRequests > 0 ? roundMilliseconds(weightedLatencyNumerator / totalRequests) : null

  return {
    status: 'measured',
    measurementType: 'api_response_time',
    service: 'Frontend fetch timings for the configured VITE_API_BASE_URL',
    units: 'milliseconds (ms)',
    sampleSize: totalRequests,
    sampleSizePerEndpoint: MEASUREMENT_SAMPLE_SIZE,
    sequentialRequests: true,
    concurrentLoad: false,
    measurementConditions:
      'Sequential requests from the browser to authenticated current-user and parcel-list endpoints using the current session token.',
    destructiveLoadTest: false,
    measuredAt: new Date().toISOString(),
    endpoints: endpointResults,
    summary: {
      successfulRequests,
      failedRequests,
      successRatePercent:
        totalRequests > 0 ? roundMilliseconds((successfulRequests / totalRequests) * 100) : null,
      weightedAverageResponseTimeMs,
      blockchainConfirmationTimeMs: null,
      blockchainStatus: 'not_measured',
      blockchainNote: 'Not measured — blockchain integration pending.',
      transactionThroughput: null,
      transactionThroughputUnit: 'transactions per second (not applicable: no transaction submission endpoint is exposed).',
      failedTransactionCount: null,
      failedTransactionNote: 'No transfer transaction workflow is currently exposed for measurement.',
    },
  }
}

export { createUnavailableMetric, normalizeNumber }