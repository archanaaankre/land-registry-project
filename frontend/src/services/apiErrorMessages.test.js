import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  GENERIC_API_ERROR_MESSAGE,
  resolveApiErrorMessage,
} from './apiErrorMessages.js'

describe('resolveApiErrorMessage', () => {
  it('maps database_unavailable server errors to a clear message', () => {
    const message = resolveApiErrorMessage(
      503,
      'database_unavailable',
      'The database is temporarily unavailable.',
    )

    assert.equal(
      message,
      'The registry data service is temporarily unavailable. Please try again shortly.',
    )
  })

  it('maps authentication_unavailable server errors to a clear message', () => {
    const message = resolveApiErrorMessage(
      503,
      'authentication_unavailable',
      'Authentication service is temporarily unavailable.',
    )

    assert.equal(
      message,
      'Authentication is temporarily unavailable. Please try again shortly.',
    )
  })

  it('ignores raw backend detail for allowlisted server errors', () => {
    const message = resolveApiErrorMessage(
      503,
      'database_unavailable',
      'psycopg2.OperationalError: connection refused at 127.0.0.1:5432',
    )

    assert.equal(
      message,
      'The registry data service is temporarily unavailable. Please try again shortly.',
    )
  })

  it('keeps the generic message for unknown server error codes', () => {
    assert.equal(
      resolveApiErrorMessage(500, 'internal_error', 'Traceback (most recent)'),
      GENERIC_API_ERROR_MESSAGE,
    )
    assert.equal(resolveApiErrorMessage(503, null, null), GENERIC_API_ERROR_MESSAGE)
    assert.equal(resolveApiErrorMessage(502, undefined, undefined), GENERIC_API_ERROR_MESSAGE)
  })

  it('passes through the API message for client errors', () => {
    assert.equal(
      resolveApiErrorMessage(401, 'invalid_credentials', 'Email or password is incorrect.'),
      'Email or password is incorrect.',
    )
  })

  it('falls back to the generic message for client errors without a message', () => {
    assert.equal(resolveApiErrorMessage(400, 'invalid_input', null), GENERIC_API_ERROR_MESSAGE)
  })
})
