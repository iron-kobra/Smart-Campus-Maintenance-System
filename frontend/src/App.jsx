import { useEffect, useMemo, useRef, useState } from 'react'
import { request, requestBlob } from './api'

const departments = [
  'Electrical',
  'Plumbing',
  'HVAC',
  'Carpentry/Furniture',
  'Cleaning',
  'IT',
  'General',
]
const roles = [
  ['student', 'Student'],
  ['maintenance', 'Maintenance'],
  ['admin', 'Admin'],
]
const initialTicket = {
  issueType: 'Lighting',
  department: 'Electrical',
  location: '',
  priority: 'Medium',
  description: '',
}
const statuses = ['All', 'Open', 'In Progress', 'Resolved']

function roleName(role) {
  return roles.find(([value]) => value === role)?.[1] || 'Account'
}

function Auth({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    role: 'student',
    department: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))

  function chooseRole(role) {
    setForm(current => ({
      ...current,
      role,
      department: role === 'maintenance' ? current.department || departments[0] : '',
    }))
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await request(`/auth/${mode === 'login' ? 'login' : 'register'}`, {
        method: 'POST',
        body: JSON.stringify(mode === 'login'
          ? { email: form.email, password: form.password, department: form.department }
          : form),
      })
      localStorage.setItem('maintenance_token', data.token)
      localStorage.setItem('maintenance_user', JSON.stringify(data.user))
      onAuthenticated(data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="brand-panel">
        <div className="brand-mark">🔧</div>
        <p className="eyebrow">CAMPUS MAINTENANCE</p>
        <h1>Every repair, in one focused workspace.</h1>
        <p>Students report problems. Administrators and maintenance teams keep every repair moving.</p>
        <div className="benefits">
          <span>24/7 reporting</span>
          <span>Department routing</span>
          {/* <span>Local MySQL data</span> */}
        </div>
      </section>
      <section className="auth-shell">
        <form className="auth-card" onSubmit={submit}>
          <div className="mobile-brand">🔧 Campus Maintenance</div>
          <h2>{mode === 'login' ? 'Welcome back' : 'Create an account'}</h2>
          <p className="muted">
            {mode === 'login'
              ? 'Sign in with the email and password for your account.'
              : 'Choose the account type that fits your work.'}
          </p>
          {mode === 'register' && (
            <label>
              Account type
              <select value={form.role} onChange={event => chooseRole(event.target.value)}>
                {roles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          )}
          {mode === 'register' && (
            <label>
              Full name
              <input
                required
                maxLength="100"
                value={form.name}
                onChange={event => update('name', event.target.value)}
                placeholder="Your name"
              />
            </label>
          )}
          {(mode === 'login' || (mode === 'register' && form.role === 'maintenance')) && (
            <label>
              {mode === 'login' ? 'Department (maintenance staff only)' : 'Maintenance department'}
              <select
                required={mode === 'register'}
                value={form.department}
                onChange={event => update('department', event.target.value)}
              >
                {mode === 'login' && <option value="">Select if you are maintenance staff</option>}
                {departments.map(department => <option key={department}>{department}</option>)}
              </select>
            </label>
          )}
          {mode === 'login' && <p className="muted">Students and admins can leave department blank.</p>}
          <label>
            Email
            <input
              required
              type="email"
              value={form.email}
              onChange={event => update('email', event.target.value)}
              pattern={mode === 'register' ? '[^@]+@iiitl\\.ac\\.in' : undefined}
              title={mode === 'register' ? 'Use your @iiitl.ac.in email address.' : undefined}
              placeholder={mode === 'register' ? 'you@iiitl.ac.in' : 'you@example.com'}
            />
          </label>
          {mode === 'register' && (
            <p className="muted"></p>
          )}
          <label>
            Password
            <input
              required
              minLength="8"
              type="password"
              value={form.password}
              onChange={event => update('password', event.target.value)}
              placeholder={mode === 'login' ? 'Your password' : 'At least 8 characters'}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary wide" disabled={loading}>
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
          <p className="switcher">
            {mode === 'login' ? "Don't have an account?" : 'Already registered?'}{' '}
            <button
              type="button"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError('')
              }}
            >
              {mode === 'login' ? 'Create one' : 'Sign in'}
            </button>
          </p>
        </form>
      </section>
    </main>
  )
}

function TicketImage({ ticketId, issueType }) {
  const [imageUrl, setImageUrl] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    let objectUrl
    requestBlob(`/tickets/${ticketId}/image`)
      .then(blob => {
        objectUrl = URL.createObjectURL(blob)
        if (active) setImageUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl)
      })
      .catch(err => {
        if (active) setError(err.message)
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [ticketId])

  if (error) return <p className="error">Attached image unavailable: {error}</p>
  if (!imageUrl) return <p className="muted">Loading attached image…</p>
  return <img className="ticket-image" src={imageUrl} alt={`Picture attached to ${issueType} report`} />
}

function Sidebar({ user, onLogout, page, setPage }) {
  const items = user.role === 'student'
    ? [['overview', 'Overview'], ['report', 'Report an issue'], ['tickets', 'My tickets']]
    : [['board', user.role === 'admin' ? 'All issues' : 'Department tickets']]

  return (
    <aside className="sidebar">
      <div className="logo">🔧 <span>Campus Maintenance<small>HELP DESK</small></span></div>
      <nav>
        {items.map(([key, label]) => (
          <button key={key} className={page === key ? 'active' : ''} onClick={() => setPage(key)}>
            {label}
          </button>
        ))}
      </nav>
      <div className="user-card">
        <strong>{user.name}</strong>
        <span>{roleName(user.role)}</span>
        {user.role === 'maintenance' && <span>{user.department}</span>}
        <button onClick={onLogout}>Sign out</button>
      </div>
    </aside>
  )
}

function TicketCard({ ticket, role, onStatus }) {
  const maintenance = role === 'maintenance'
  const isAdmin = role === 'admin'
  const next = ticket.status === 'Open'
    ? ['In Progress', 'Start work']
    : ticket.status === 'In Progress'
      ? ['Resolved', 'Mark resolved']
      : ['In Progress', 'Reopen']

  return (
    <article className="ticket">
      <div className="ticket-main">
        <div className="ticket-title">
          <h3>{ticket.issueType}</h3>
          <span className={`pill ${ticket.status.toLowerCase().replaceAll(' ', '-')}`}>
            {ticket.status}
          </span>
          <span className="priority">{ticket.priority}</span>
        </div>
        <p>{ticket.description}</p>
        {ticket.hasImage && <TicketImage ticketId={ticket.id} issueType={ticket.issueType} />}
        <div className="metadata">
          <span>📍 {ticket.location}</span>
          <span>🏢 {ticket.department}</span>
          <span>◷ {new Date(ticket.createdAt).toLocaleString()}</span>
          {(maintenance || isAdmin) && (
            <span>👤 {ticket.reporterName}{isAdmin ? ` (${ticket.reporterEmail})` : ''}</span>
          )}
        </div>
      </div>
      {maintenance && (
        <button className="secondary" onClick={() => onStatus(ticket.id, next[0])}>
          {next[1]}
        </button>
      )}
    </article>
  )
}

function Overview({ user, tickets, setPage }) {
  const count = status => tickets.filter(ticket => ticket.status === status).length
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">STUDENT WORKSPACE</p>
          <h1>Hello, {user.name}</h1>
          <p className="muted">Report a campus problem and follow its repair progress.</p>
        </div>
        <button className="primary" onClick={() => setPage('report')}>+ Report an issue</button>
      </div>
      <div className="stats">
        <div><span>Open tickets</span><strong>{count('Open')}</strong></div>
        <div><span>Being worked on</span><strong>{count('In Progress')}</strong></div>
        <div><span>Resolved</span><strong>{count('Resolved')}</strong></div>
      </div>
      <section className="callout">
        <h2>See something that needs attention?</h2>
        <p>Tell the team what happened, where it is, and which department can help.</p>
        <button className="light-button" onClick={() => setPage('report')}>Report an issue →</button>
      </section>
    </>
  )
}

function Report({ onCreated }) {
  const [form, setForm] = useState(initialTicket)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [image, setImage] = useState(null)
  const imageInput = useRef(null)

  async function submit(event) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const payload = new FormData()
      Object.entries(form).forEach(([key, value]) => payload.append(key, value))
      if (image) payload.append('image', image)
      const data = await request('/tickets', { method: 'POST', body: payload })
      onCreated(data.ticket)
      setForm(initialTicket)
      setImage(null)
      if (imageInput.current) imageInput.current.value = ''
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="form-card">
      <p className="eyebrow">NEW TICKET</p>
      <h1>Report a maintenance issue</h1>
      <p className="muted">Give the team enough detail to find and repair the problem quickly.</p>
      <form onSubmit={submit}>
        <label>
          Issue type
          <select
            value={form.issueType}
            onChange={event => setForm(current => ({ ...current, issueType: event.target.value }))}
          >
            {['Lighting', 'Air conditioning', 'Water / plumbing', 'Electrical', 'Furniture', 'Other']
              .map(type => <option key={type}>{type}</option>)}
          </select>
        </label>
        <label>
          Responsible department
          <select
            required
            value={form.department}
            onChange={event => setForm(current => ({ ...current, department: event.target.value }))}
          >
            {departments.map(department => <option key={department}>{department}</option>)}
          </select>
        </label>
        <label>
          Location
          <input
            required
            maxLength="200"
            value={form.location}
            onChange={event => setForm(current => ({ ...current, location: event.target.value }))}
            placeholder="e.g. Academic Block A, Room 204"
          />
        </label>
        <label>
          Urgency
          <select
            value={form.priority}
            onChange={event => setForm(current => ({ ...current, priority: event.target.value }))}
          >
            {['Low', 'Medium', 'High', 'Critical'].map(priority => <option key={priority}>{priority}</option>)}
          </select>
        </label>
        <label>
          What is happening?
          <textarea
            required
            rows="5"
            value={form.description}
            onChange={event => setForm(current => ({ ...current, description: event.target.value }))}
            placeholder="Describe the issue and anything that helps the team reproduce it."
          />
        </label>
        <label htmlFor="ticket-image">Attach a picture (optional, JPEG/PNG/WebP; max 5 MB)</label>
        <input
          ref={imageInput}
          id="ticket-image"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={event => {
            const file = event.target.files?.[0] || null
            if (file && file.size > 5 * 1024 * 1024) {
              setImage(null)
              setError('The image must be 5 MB or smaller.')
              event.target.value = ''
              return
            }
            setError('')
            setImage(file)
          }}
        />
        {image && <p className="muted">Selected: {image.name}</p>}
        {error && <p className="error">{error}</p>}
        <button className="primary wide" disabled={saving}>
          {saving ? 'Submitting…' : 'Submit ticket'}
        </button>
      </form>
    </section>
  )
}

function Tickets({ tickets, role, department, onStatus }) {
  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const maintenance = role === 'maintenance'
  const visible = useMemo(
    () => tickets.filter(ticket =>
      (filter === 'All' || ticket.status === filter)
      && `${ticket.issueType} ${ticket.department} ${ticket.location} ${ticket.description} ${ticket.reporterName || ''}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ),
    [tickets, filter, query],
  )
  const heading = role === 'admin' ? 'All reported issues' : maintenance ? 'Department ticket board' : 'My tickets'

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{roleName(role).toUpperCase()} WORKSPACE</p>
          <h1>{heading}</h1>
          <p className="muted">
            {role === 'admin'
              ? 'Review all maintenance requests and the students who reported them.'
              : maintenance
                ? `Review and update requests assigned to the ${department} department.`
                : 'Track every issue you have reported.'}
          </p>
        </div>
      </div>
      <div className="toolbar">
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search tickets" />
        {statuses.map(status => (
          <button
            key={status}
            className={filter === status ? 'filter active-filter' : 'filter'}
            onClick={() => setFilter(status)}
          >
            {status}
          </button>
        ))}
      </div>
      <div className="tickets">
        {visible.length
          ? visible.map(ticket => (
            <TicketCard key={ticket.id} ticket={ticket} role={role} onStatus={onStatus} />
          ))
          : <div className="empty"><strong>No matching tickets</strong><p>Tickets that match your search and filter will appear here.</p></div>}
      </div>
    </>
  )
}

export default function App() {
  const [user, setUser] = useState(() => {
    try {
      const savedUser = JSON.parse(localStorage.getItem('maintenance_user'))
      if (
        !savedUser
        || !roles.some(([role]) => role === savedUser.role)
        || (savedUser.role === 'maintenance' && !savedUser.department)
      ) {
        localStorage.removeItem('maintenance_token')
        localStorage.removeItem('maintenance_user')
        return null
      }
      return savedUser
    } catch {
      localStorage.removeItem('maintenance_token')
      localStorage.removeItem('maintenance_user')
      return null
    }
  })
  const [tickets, setTickets] = useState([])
  const [page, setPage] = useState('overview')
  const [error, setError] = useState('')

  function logout() {
    localStorage.removeItem('maintenance_token')
    localStorage.removeItem('maintenance_user')
    setUser(null)
    setTickets([])
  }

  function showError(err) {
    if (err.status === 401) {
      logout()
      return
    }
    setError(err.message)
  }

  async function loadTickets() {
    try {
      setError('')
      const data = await request('/tickets')
      setTickets(data.tickets)
    } catch (err) {
      showError(err)
    }
  }

  useEffect(() => {
    if (user) {
      setPage(user.role === 'student' ? 'overview' : 'board')
      loadTickets()
    }
  }, [user])

  if (!user) return <Auth onAuthenticated={setUser} />

  async function updateStatus(id, status) {
    try {
      const data = await request(`/tickets/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      })
      setTickets(current => current.map(ticket => ticket.id === id ? data.ticket : ticket))
    } catch (err) {
      showError(err)
    }
  }

  function created(ticket) {
    setTickets(current => [ticket, ...current])
    setPage('tickets')
  }

  const workspaceName = user.role === 'admin' ? 'Administrator portal' : `${roleName(user.role)} portal`

  return (
    <div className="app">
      <Sidebar user={user} onLogout={logout} page={page} setPage={setPage} />
      <main className="content">
        <header><p>Campus Maintenance</p><h2>{workspaceName}</h2></header>
        {error && <p className="error banner">{error}</p>}
        {user.role === 'admin' || user.role === 'maintenance'
          ? <Tickets tickets={tickets} role={user.role} department={user.department} onStatus={updateStatus} />
          : page === 'overview'
            ? <Overview user={user} tickets={tickets} setPage={setPage} />
            : page === 'report'
              ? <Report onCreated={created} />
              : <Tickets tickets={tickets} role={user.role} department={user.department} onStatus={updateStatus} />}
      </main>
    </div>
  )
}
