import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  OWNERSHIP_STATUSES,
  activeShare,
  generateOwnershipId,
  validateIdentifier,
  validateOwnershipForm,
  validateShare,
} from './ownershipValidation.js'

describe('validateIdentifier', () => {
  it('rejects empty identifiers', () => {
    assert.equal(validateIdentifier('', 'Owner ID').ok, false)
    assert.equal(validateIdentifier('   ', 'Owner ID').ok, false)
    assert.equal(validateIdentifier(undefined, 'Owner ID').ok, false)
  })

  it('rejects invalid characters and overlength values', () => {
    assert.equal(validateIdentifier('bad owner', 'Owner ID').ok, false)
    assert.equal(validateIdentifier('bad!owner', 'Owner ID').ok, false)
    assert.equal(validateIdentifier('a'.repeat(65), 'Owner ID').ok, false)
  })

  it('accepts backend-pattern identifiers', () => {
    assert.equal(validateIdentifier('citizen-1', 'Owner ID').value, 'citizen-1')
    assert.equal(validateIdentifier('own_1-2', 'Owner ID').value, 'own_1-2')
    assert.equal(validateIdentifier('ownership-abc123', 'Ownership ID').value, 'ownership-abc123')
  })
})

describe('validateShare', () => {
  it('rejects missing, zero, negative, and over-100 shares', () => {
    assert.equal(validateShare('').ok, false)
    assert.equal(validateShare('0').ok, false)
    assert.equal(validateShare('-5').ok, false)
    assert.equal(validateShare('100.5').ok, false)
    assert.equal(validateShare('101').ok, false)
  })

  it('rejects non-numeric and over-precision input', () => {
    assert.equal(validateShare('abc').ok, false)
    assert.equal(validateShare('1.1234567').ok, false)
  })

  it('accepts valid shares and returns numbers', () => {
    assert.equal(validateShare('100').value, 100)
    assert.equal(validateShare('50.5').value, 50.5)
    assert.equal(validateShare('33.333333').value, 33.333333)
    assert.equal(validateShare('0.000001').value, 0.000001)
  })
})

describe('validateOwnershipForm', () => {
  const validForm = {
    parcel_id: 'parcel-1',
    ownership_id: 'ownership-abc123',
    owner_id: 'citizen-1',
    share: '100',
    status: 'ACTIVE',
  }

  it('builds the exact API payload and nothing more', () => {
    const result = validateOwnershipForm(validForm)

    assert.equal(result.ok, true)
    assert.deepEqual(result.payload, {
      ownership_id: 'ownership-abc123',
      parcel_id: 'parcel-1',
      owner_id: 'citizen-1',
      share: 100,
      status: 'ACTIVE',
    })
  })

  it('rejects unknown statuses', () => {
    assert.equal(validateOwnershipForm({ ...validForm, status: 'UNKNOWN' }).ok, false)
    assert.ok(OWNERSHIP_STATUSES.includes('ACTIVE'))
  })

  it('returns the first failing field error', () => {
    const result = validateOwnershipForm({ ...validForm, parcel_id: '' })
    assert.equal(result.ok, false)
    assert.match(result.error, /Parcel ID/)
  })
})

describe('generateOwnershipId', () => {
  it('generates backend-pattern identifiers', () => {
    const id = generateOwnershipId(() => 'fixedseed')
    assert.match(id, /^ownership-[a-z0-9]+-fixedseed$/)
  })
})

describe('activeShare', () => {
  it('sums only active ownership shares', () => {
    const total = activeShare([
      { status: 'ACTIVE', share: '60.5' },
      { status: 'INACTIVE', share: '30' },
      { status: 'ACTIVE', share: '10' },
    ])
    assert.equal(total, 70.5)
  })

  it('returns 0 for empty or malformed input', () => {
    assert.equal(activeShare([]), 0)
    assert.equal(activeShare(undefined), 0)
  })
})
