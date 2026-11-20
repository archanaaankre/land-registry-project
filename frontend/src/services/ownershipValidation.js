// Pure validation helpers for the ownership creation form.
// Kept free of service/API imports so the node test runner can exercise them.

export const OWNERSHIP_STATUSES = ['ACTIVE', 'INACTIVE', 'DISPUTED']

const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/
const SHARE_PATTERN = /^\d{1,3}(\.\d{1,6})?$/

export function generateOwnershipId(seed) {
  const random =
    typeof seed === 'function' ? seed() : Math.random().toString(36).slice(2, 8)
  return `ownership-${Date.now().toString(36)}-${random}`
}

export function validateIdentifier(value, label) {
  const trimmed = typeof value === 'string' ? value.trim() : ''
  if (!trimmed) {
    return { ok: false, error: `${label} is required.` }
  }
  if (trimmed.length > 64 || !IDENTIFIER_PATTERN.test(trimmed)) {
    return {
      ok: false,
      error: `${label} is invalid. Use letters, numbers, hyphens, and underscores (up to 64 characters).`,
    }
  }
  return { ok: true, value: trimmed }
}

export function validateShare(value) {
  const trimmed =
    typeof value === 'string' ? value.trim() : String(value ?? '').trim()
  if (!trimmed) {
    return { ok: false, error: 'Share is required.' }
  }
  if (!SHARE_PATTERN.test(trimmed)) {
    return {
      ok: false,
      error: 'Share must be a number with up to 6 decimal places.',
    }
  }
  const numeric = Number(trimmed)
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return { ok: false, error: 'Share must be greater than zero.' }
  }
  if (numeric > 100) {
    return { ok: false, error: 'Share must not exceed 100.' }
  }
  return { ok: true, value: numeric }
}

export function validateOwnershipStatus(value) {
  if (!OWNERSHIP_STATUSES.includes(value)) {
    return { ok: false, error: 'Select a valid ownership status.' }
  }
  return { ok: true, value }
}

export function validateOwnershipForm(data) {
  const parcel = validateIdentifier(data?.parcel_id, 'Parcel ID')
  if (!parcel.ok) return parcel

  const ownershipId = validateIdentifier(data?.ownership_id, 'Ownership ID')
  if (!ownershipId.ok) return ownershipId

  const ownerId = validateIdentifier(data?.owner_id, 'Owner ID')
  if (!ownerId.ok) return ownerId

  const share = validateShare(data?.share)
  if (!share.ok) return share

  const status = validateOwnershipStatus(data?.status)
  if (!status.ok) return status

  return {
    ok: true,
    payload: {
      ownership_id: ownershipId.value,
      parcel_id: parcel.value,
      owner_id: ownerId.value,
      share: share.value,
      status: status.value,
    },
  }
}

export function activeShare(records) {
  if (!Array.isArray(records)) {
    return 0
  }
  return records
    .filter((record) => record?.status === 'ACTIVE')
    .reduce((total, record) => total + Number(record?.share ?? 0), 0)
}
