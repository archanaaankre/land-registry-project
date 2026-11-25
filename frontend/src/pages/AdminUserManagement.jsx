import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import {
  createAdminUser,
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
} from '../services/adminService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

const ROLES = ['REGISTRAR', 'VERIFICATION_OFFICER']

export default function AdminUserManagement() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [filterActive, setFilterActive] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  // Create user form state
  const [createOpen, setCreateOpen] = useState(false)
  const [newUser, setNewUser] = useState({
    name: '',
    email: '',
    password: '',
    role: 'REGISTRAR',
  })
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  // Edit role state
  const [editingRole, setEditingRole] = useState('')
  const [editRoleError, setEditRoleError] = useState('')
  const [roleProcessing, setRoleProcessing] = useState({})

  // Edit active state
  const [editActiveError, setEditActiveError] = useState('')
  const [activeProcessing, setActiveProcessing] = useState({})
  const [copyFeedback, setCopyFeedback] = useState(null)

  const loadUsers = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const items = await listAdminUsers({
        signal,
        search: search || undefined,
        role: filterRole || undefined,
        isActive: filterActive === 'true' ? true : filterActive === 'false' ? false : undefined,
      })
      if (!signal.aborted) {
        setUsers(items)
        setError('')
      }
    } catch (requestError) {
      if (requestError.name === 'AbortError' || signal.aborted) {
        return
      }
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      if (!signal.aborted) {
        setUsers([])
        setError(
          requestError.message || 'We couldn’t load user accounts. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false)
      }
    }
  }, [logout, navigate, search, filterRole, filterActive])

  useEffect(() => {
    const controller = new AbortController()
    async function loadUsersData() {
      await loadUsers(controller.signal)
    }
    loadUsersData()
    return () => controller.abort()
  }, [loadUsers, reloadKey])

  function reloadUsers() {
    setError('')
    setReloadKey((current) => current + 1)
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  async function handleCreateUser(event) {
    event.preventDefault()
    if (creating) return
    setCreateError('')
    setCreating(true)
    try {
      await createAdminUser(newUser)
      setCreateOpen(false)
      setNewUser({ name: '', email: '', password: '', role: 'REGISTRAR' })
      reloadUsers()
    } catch (requestError) {
      setCreateError(
        requestError.message || 'The user account could not be created. Please try again.',
      )
    } finally {
      setCreating(false)
    }
  }

  async function handleUpdateRole(userId, newRole) {
    setEditingRole(userId)
    setEditRoleError('')
    setRoleProcessing((current) => ({ ...current, [userId]: true }))
    try {
      await updateAdminUserRole(userId, newRole)
      reloadUsers()
    } catch (requestError) {
      setEditRoleError(
        requestError.message || 'The user role could not be updated. Please try again.',
      )
    } finally {
      setRoleProcessing((current) => {
        const next = { ...current }
        delete next[userId]
        return next
      })
      setEditingRole('')
    }
  }

  async function handleToggleActive(userId, currentActive) {
    setActiveProcessing((current) => ({ ...current, [userId]: true }))
    setEditActiveError('')
    try {
      await updateAdminUserStatus(userId, !currentActive)
      reloadUsers()
    } catch (requestError) {
      setEditActiveError(
        requestError.message || 'The account status could not be updated. Please try again.',
      )
    } finally {
      setActiveProcessing((current) => {
        const next = { ...current }
        delete next[userId]
        return next
      })
    }
  }

  async function handleCopyUserId(userId) {
    try {
      await navigator.clipboard.writeText(userId)
      setCopyFeedback({ userId, message: 'User ID copied.' })
    } catch {
      setCopyFeedback({
        userId,
        message: 'Clipboard unavailable. Select and copy the ID.',
      })
    }
  }

  return (
    <main className="registry-page admin-user-management-page">
      <PageHeader
        actions={
          <div className="dashboard-navigation">
            <button
              className="secondary-button"
              onClick={() => setCreateOpen((open) => !open)}
              type="button"
            >
              {createOpen ? 'Close form' : 'Create User'}
            </button>
            <Link className="text-link" to="/admin/dashboard">Back to dashboard</Link>
          </div>
        }
        eyebrow="User management"
        intro="Create, view, and manage registrar and verification officer accounts."
        title="Manage Users"
      />

      <nav className="dashboard-links" aria-label="Account navigation">
        <div className="dashboard-navigation">
          <Link to="/admin/dashboard">Back to admin dashboard</Link>
        </div>
        <button className="secondary-button" onClick={handleLogout} type="button">
          Sign out
        </button>
      </nav>

      {createOpen && (
        <section className="registry-state parcel-registration-form" aria-labelledby="create-user-heading">
          <h3 id="create-user-heading">Create a new user account</h3>
          {createError && (
            <p className="registry-state error-state" role="alert">{createError}</p>
          )}
          <form className="auth-form" onSubmit={handleCreateUser}>
            <label>
              Full name
              <input
                autoComplete="name"
                maxLength={100}
                onChange={(event) =>
                  setNewUser((current) => ({ ...current, name: event.target.value }))
                }
                required
                type="text"
                value={newUser.name}
              />
            </label>
            <label>
              Email address
              <input
                autoComplete="email"
                onChange={(event) =>
                  setNewUser((current) => ({
                    ...current,
                    email: event.target.value.trim().toLowerCase(),
                  }))
                }
                required
                type="email"
                value={newUser.email}
              />
            </label>
            <label>
              Password
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={8}
                onChange={(event) =>
                  setNewUser((current) => ({ ...current, password: event.target.value }))
                }
                required
                type="password"
                value={newUser.password}
              />
            </label>
            <label>
              Role
              <select
                onChange={(event) =>
                  setNewUser((current) => ({ ...current, role: event.target.value }))
                }
                required
                value={newUser.role}
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </label>
            <div className="parcel-registration-actions">
              <button className="primary-button" disabled={creating} type="submit">
                {creating ? 'Creating…' : 'Create user'}
              </button>
              <button
                className="secondary-button"
                disabled={creating}
                onClick={() => setCreateOpen(false)}
                type="button"
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="registry-panel" aria-labelledby="users-list-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="users-list-heading">Registered users</h2>
            {!loading && !error && (
              <p className="result-count">
                {users.length} user{users.length === 1 ? '' : 's'}
              </p>
            )}
          </div>
          <div className="user-toolbar-actions">
            <label className="search-field">
              <span>Search users</span>
              <input
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name or email…"
                type="search"
                value={search}
              />
            </label>
            <select
              onChange={(event) => setFilterRole(event.target.value)}
              value={filterRole}
            >
              <option value="">All roles</option>
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <select
              onChange={(event) => setFilterActive(event.target.value)}
              value={filterActive}
            >
              <option value="">All accounts</option>
              <option value="true">Active</option>
              <option value="false">Deactivated</option>
            </select>
            <button
              className="secondary-button"
              onClick={reloadUsers}
              type="button"
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && <p className="registry-state" role="status">Loading users…</p>}
        {!loading && error && (
          <div className="registry-state error-state" role="alert">
            <p>{error}</p>
            <button
              className="secondary-button"
              onClick={reloadUsers}
              type="button"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && users.length === 0 && (
          <p className="registry-state">No users are currently available.</p>
        )}
        {!loading && !error && users.length > 0 && (
          <div className="ownership-list">
            {users.map((userItem) => (
              <article className="ownership-record" key={userItem.id}>
                <dl>
                  <div>
                    <dt>User ID</dt>
                    <dd>
                      <div className="admin-user-id-control">
                        <code className="admin-user-id">{userItem.id}</code>
                        <button
                          aria-label={`Copy user ID for ${userItem.name}`}
                          className="secondary-button admin-user-id-copy"
                          onClick={() => handleCopyUserId(userItem.id)}
                          type="button"
                        >
                          {copyFeedback?.userId === userItem.id ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                      {copyFeedback?.userId === userItem.id && (
                        <span
                          className="admin-user-id-feedback"
                          role={
                            copyFeedback.message === 'User ID copied.'
                              ? 'status'
                              : 'alert'
                          }
                        >
                          {copyFeedback.message}
                        </span>
                      )}
                    </dd>
                  </div>
                  <div><dt>Name</dt><dd>{userItem.name}</dd></div>
                  <div><dt>Email</dt><dd>{userItem.email}</dd></div>
                  <div><dt>Role</dt><dd>{userItem.role}</dd></div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span
                        className={`status-badge ${
                          userItem.is_active ? 'status-active' : 'status-inactive'
                        }`}
                      >
                        {userItem.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </dd>
                  </div>
                  <div><dt>Created</dt><dd>{userItem.created_at || 'Not available'}</dd></div>
                </dl>
                <div className="user-actions">
                  {ROLES.map((role) => (
                    <button
                      key={role}
                      className="secondary-button"
                      disabled={editingRole === userItem.id || roleProcessing[userItem.id]}
                      onClick={() => handleUpdateRole(userItem.id, role)}
                      type="button"
                    >
                      {editingRole === userItem.id ? 'Updating…' : `Set ${role}`}
                    </button>
                  ))}
                  <button
                    className="secondary-button"
                    disabled={activeProcessing[userItem.id]}
                    onClick={() => handleToggleActive(userItem.id, userItem.is_active)}
                    type="button"
                  >
                    {activeProcessing[userItem.id] ? 'Updating…' : userItem.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}

        {editRoleError && (
          <div className="registry-state error-state" role="alert">
            <p>{editRoleError}</p>
          </div>
        )}
        {editActiveError && (
          <div className="registry-state error-state" role="alert">
            <p>{editActiveError}</p>
          </div>
        )}
      </section>
    </main>
  )
}
