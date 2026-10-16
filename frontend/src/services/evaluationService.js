import { ApiError, apiGet } from './api.js'
import { listParcels, getParcelOwnership } from './parcelService.js'

const MEASUREMENT_SAMPLE_SIZE = 5
const PERFORMANCE_ENDPOINTS = [
  {
    key: 'health',
    label: 'Health endpoint',
    path: '/health',
    requiresAuthentication: false,
  },
  {
    key: 'auth-me',
    label: 'Current-user endpoint',
    path: '/auth/me',
    requiresAuthentication: true,
  },
  {
    key: 'parcels',
    label: 'Parcel list endpoint',
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

export function getTamperDetectionSummary() {
  return createUnavailableMetric(
    'not_implemented',
    {
      title: 'Tamper detection',
      message:
        'No tamper-detection test runner, modified-document comparison, or unauthorized ownership-update workflow is implemented in this build. Counts and detection rates are therefore not available.',
      formula:
        'Detection rate = correctly detected tampering attempts / total tampering attempts tested x 100',
      denominatorRule: 'Only tampering attempts belong in the denominator; original-record integrity checks are reported separately.',
    },
  )
}

export function getDocumentIntegritySummary() {
  return createUnavailableMetric(
    'not_implemented',
    {
      title: 'Document integrity',
      message:
        'No document upload, storage, cryptographic hashing, or hash-verification endpoint is implemented in this build. No hashes or verification results are available.',
      disclaimer:
        'A matching cryptographic hash establishes content consistency with a recorded hash. It does not establish the document’s legal authenticity.',
    },
  )
}

export const ACCESS_CONTROL_POLICY = {
  source: 'Backend authorization constants and protected routes (app/registry/authorization.py, app/auth/decorators.py).',
  roles: ['CITIZEN', 'REGISTRAR', 'ADMIN'],
  actions: [
    {
      key: 'view-parcels',
      label: 'View parcels and parcel details',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'ADMIN'],
      notes: 'GET /api/parcels and GET /api/parcels/:parcelId use PARCEL_READ_ROLES.',
    },
    {
      key: 'view-ownership',
      label: 'View ownership records for a parcel',
      allowedRoles: ['CITIZEN', 'REGISTRAR', 'ADMIN'],
      notes: 'GET /api/parcels/:parcelId/ownership uses OWNERSHIP_READ_ROLES.',
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
  ],
  measuredResults: null,
}

export function getAccessControlSummary() {
  return {
    status: 'policy_only',
    policy: ACCESS_CONTROL_POLICY,
    message:
      'The matrix below reflects configured backend authorization rules. No RBAC test result dataset or unauthorized-attempt report is exposed by the API.',
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
    return {
      status: 'unavailable',
      source: 'GET /api/parcels',
      parcels: [],
      events: [],
      errors: [describeBackendError(error, 'parcel list')],
      message:
        'Parcel and ownership records cannot be loaded from the backend. This is the expected state when the registry repository is not configured.',
    }
  }

  const ownershipResults = await Promise.allSettled(
    parcels.map(async (parcel) => {
      const records = await getParcelOwnership(parcel.parcel_id, { signal })
      return { parcel, records }
    }),
  )

  const events = []
  const lastOwnerByParcel = new Map()

  for (const result of ownershipResults) {
    if (result.status === 'rejected') {
      if (result.reason?.name === 'AbortError') {
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
      const previousOwner = lastOwnerByParcel.get(parcel.parcel_id) ?? null
      events.push({
        id: `${parcel.parcel_id}-${record.ownership_id}-${record.created_at}`,
        parcelId: parcel.parcel_id,
        cadastralNumber: parcel.cadastral_number,
        ownerReference: record.owner_id,
        previousOwnerReference: previousOwner,
        eventType: 'Ownership record available',
        timestamp: record.created_at,
        recordStatus: record.status,
        share: record.share,
        transactionId: null,
        blockchainConfirmation: 'not_available',
      })
      lastOwnerByParcel.set(parcel.parcel_id, record.owner_id)
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
        ? 'No parcel records are currently available from the backend.'
        : 'Events are generated from recorded ownership rows. No transfer workflow or blockchain transaction ID is exposed by the current backend.',
  }
}

function describeBackendError(error, subject) {
  if (error?.status === 503 || error?.code === 'registry_unavailable') {
    return `The ${subject} registry is temporarily unavailable.`
  }
  return `${subject}: ${error?.message ?? 'Request failed'}`
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
        failedRequests: MEASUREMENT_SAMPLE_SIZE,
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
      'Sequential requests from the browser to the configured backend origin. No authentication header is sent to /health; authenticated endpoints use the current session token.',
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