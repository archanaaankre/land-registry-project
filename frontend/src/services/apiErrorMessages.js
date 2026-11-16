export const GENERIC_API_ERROR_MESSAGE =
  'This request could not be completed. Please try again.'

// User-facing copy for the specific service-unavailable error codes the API
// documents. Only these allowlisted 5xx codes are surfaced with their own
// message; every other server error keeps the generic message so database
// names, connection details, SQL, and exception text can never reach the UI.
const SERVICE_UNAVAILABLE_MESSAGES = {
  authentication_unavailable:
    'Authentication is temporarily unavailable. Please try again shortly.',
  database_unavailable:
    'The registry data service is temporarily unavailable. Please try again shortly.',
}

export function resolveApiErrorMessage(status, code, apiMessage) {
  if (status >= 500) {
    return SERVICE_UNAVAILABLE_MESSAGES[code] || GENERIC_API_ERROR_MESSAGE
  }
  return apiMessage || GENERIC_API_ERROR_MESSAGE
}
