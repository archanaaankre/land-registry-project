import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeader from '../components/layout/PageHeader.jsx'
import { useAuth } from '../context/useAuth.js'
import {
  createAdminUser,
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
} from '../services/adminUserService.js'
import './AdminUsers.css'

const ASSIGNABLE_ROLES = ['REGISTRAR', 'VERIFICATION_OFFICER']
const ALL_ROLES = ['CITIZEN', ...ASSIGNABLE_ROLES, 'ADMIN']
const EMPTY_FORM = {
  name: '',
  email: '',
  password: '',
  role: 'REGISTRAR',
}

export default function AdminUsers() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [roleEdits, setRoleEdits] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [busyUserId, setBusyUserId] = useState('')
  const [error, setError] = useState('')
  const [listError, setListError] = useState('')
  const [success, setSuccess] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const handleUnauthorized = useCallback(() => {
    logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()

    listAdminUsers({
      role: roleFilter,
      isActive: statusFilter,
      signal: controller.signal,
    })
      .then(setUsers)
      .catch((requestError) => {
        if (requestError.name === 'AbortError') return
        if (requestError.status === 401) {
          handleUnauthorized()
          return
        }
        setListError(requestError.message || 'Could not load users. Please try again.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [roleFilter, statusFilter, reloadKey, handleUnauthorized])

  function refreshUsers(message) {
    setSuccess(message)
    setError('')
    setListError('')
    setLoading(true)
    setReloadKey((current) => current + 1)
  }

  function retryUserList() {
    setListError('')
    setLoading(true)
    setReloadKey((current) => current + 1)
  }

  function handleRoleFilterChange(event) {
    setError('')
    setListError('')
    setLoading(true)
    setRoleFilter(event.target.value)
  }

  function handleStatusFilterChange(event) {
    setError('')
    setListError('')
    setLoading(true)
    setStatusFilter(event.target.value)
  }

  async function handleCreateUser(event) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const created = await createAdminUser({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
      })
      setForm(EMPTY_FORM)
      refreshUsers(`${created.name} was created successfully.`)
    } catch (requestError) {
      if (requestError.status === 401) {
        handleUnauthorized()
        return
      }
      setError(requestError.message || 'Could not create the user.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRoleUpdate(user) {
    const role = roleEdits[user.id] || user.role
    if (role === user.role) return
    setBusyUserId(user.id)
    setError('')
    setSuccess('')
    try {
      const updated = await updateAdminUserRole(user.id, role)
      setRoleEdits((current) => {
        const next = { ...current }
        delete next[user.id]
        return next
      })
      refreshUsers(`${updated.name}'s role was updated.`)
    } catch (requestError) {
      if (requestError.status === 401) {
        handleUnauthorized()
        return
      }
      setError(requestError.message || 'Could not update the role.')
    } finally {
      setBusyUserId('')
    }
  }

  async function handleStatusUpdate(user) {
    const isActive = !user.is_active
    if (
      !isActive &&
      !window.confirm(`Deactivate ${user.name}? They will lose access immediately.`)
    ) {
      return
    }
    setBusyUserId(user.id)
    setError('')
    setSuccess('')
    try {
      const updated = await updateAdminUserStatus(user.id, isActive)
      refreshUsers(
        `${updated.name} was ${updated.is_active ? 'activated' : 'deactivated'}.`,
      )
    } catch (requestError) {
      if (requestError.status === 401) {
        handleUnauthorized()
        return
      }
      setError(requestError.message || 'Could not update account status.')
    } finally {
      setBusyUserId('')
    }
  }

  return (
    <main className="registry-page admin-users-page">
      <PageHeader
        eyebrow="Administration"
        intro="Create staff accounts and manage user roles and account access."
        title="User management"
      />

      {error && <p className="registry-state error-state" role="alert">{error}</p>}
      {success && <p className="registry-state parcel-success" role="status">{success}</p>}

      <section className="registry-panel admin-create-panel" aria-labelledby="create-user-heading">
        <div className="admin-section-heading">
          <div>
            <h2 id="create-user-heading">Create staff account</h2>
            <p>New accounts are active. Public citizen registration remains separate.</p>
          </div>
        </div>
        <form className="auth-form admin-create-form" onSubmit={handleCreateUser}>
          <label>
            Name
            <input
              autoComplete="name"
              maxLength={100}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              required
              value={form.name}
            />
          </label>
          <label>
            Email
            <input
              autoComplete="email"
              onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
              required
              type="email"
              value={form.email}
            />
          </label>
          <label>
            Temporary password
            <input
              autoComplete="new-password"
              maxLength={128}
              minLength={8}
              onChange={(event) =>
                setForm((current) => ({ ...current, password: event.target.value }))
              }
              required
              type="password"
              value={form.password}
            />
          </label>
          <label>
            Role
            <select
              onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))}
              value={form.role}
            >
              {ASSIGNABLE_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
          </label>
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>
      </section>

      <section className="registry-panel" aria-labelledby="users-heading">
        <div className="admin-section-heading admin-users-toolbar">
          <div>
            <h2 id="users-heading">Users</h2>
            {!loading && !error && (
              <p>{users.length} {users.length === 1 ? 'account' : 'accounts'}</p>
            )}
          </div>
          <div className="admin-user-filters">
            <label>
              Role
              <select onChange={handleRoleFilterChange} value={roleFilter}>
                <option value="">All roles</option>
                {ALL_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </label>
            <label>
              Account status
              <select
                onChange={handleStatusFilterChange}
                value={statusFilter}
              >
                <option value="">All statuses</option>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </select>
            </label>
          </div>
        </div>

        {loading ? (
          <p className="registry-state" role="status">Loading users…</p>
        ) : listError ? (
          <div className="registry-state error-state">
            <p role="alert">{listError}</p>
            <button className="secondary-button" onClick={retryUserList} type="button">
              Retry
            </button>
          </div>
        ) : users.length === 0 ? (
          <p className="registry-state">No users match these filters.</p>
        ) : (
          <div className="admin-user-table-wrap">
            <table className="admin-user-table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Account status</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const isBusy = busyUserId === user.id
                  const selectedRole = roleEdits[user.id] || user.role
                  return (
                    <tr key={user.id}>
                      <td data-label="Name">{user.name}</td>
                      <td data-label="Email" className="admin-user-email">{user.email}</td>
                      <td data-label="Role">
                        <label className="sr-only" htmlFor={`role-${user.id}`}>Role for {user.name}</label>
                        <select
                          id={`role-${user.id}`}
                          onChange={(event) =>
                            setRoleEdits((current) => ({
                              ...current,
                              [user.id]: event.target.value,
                            }))
                          }
                          value={selectedRole}
                        >
                          {ALL_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
                        </select>
                      </td>
                      <td data-label="Account status">
                        <span className={`admin-status ${user.is_active ? 'is-active' : 'is-inactive'}`}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td data-label="Actions">
                        <div className="admin-user-actions">
                          <button
                            className="secondary-button"
                            disabled={isBusy || selectedRole === user.role}
                            onClick={() => handleRoleUpdate(user)}
                            type="button"
                          >
                            Change role
                          </button>
                          <button
                            className={user.is_active ? 'admin-danger-button' : 'secondary-button'}
                            disabled={isBusy}
                            onClick={() => handleStatusUpdate(user)}
                            type="button"
                          >
                            {user.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
