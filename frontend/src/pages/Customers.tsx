import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Customer, Page } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Card, ErrorNote, Loading, Pager } from '../components/ui'
import { shortId, when } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export function Customers() {
  const { hasRole } = useAuth()
  return hasRole('ADMIN', 'ANALYST') ? <StaffView isAdmin={hasRole('ADMIN')} /> : <OwnProfile />
}

function OwnProfile() {
  const { data, error, loading } = useAsync(() => api<Customer>('/api/customers/me'), [])
  return (
    <>
      <h1>My profile</h1>
      <ErrorNote error={error} />
      {loading && !data ? <Loading what="profile" /> : data && (
        <Card>
          <dl className="grid">
            <dt>Name</dt><dd>{data.firstName} {data.lastName}</dd>
            <dt>Email</dt><dd>{data.email}</dd>
            <dt>Country</dt><dd>{data.country}</dd>
            <dt>Segment</dt><dd>{data.segment}</dd>
          </dl>
        </Card>
      )}
    </>
  )
}

function StaffView({ isAdmin }: { isAdmin: boolean }) {
  const [page, setPage] = useState(0)
  const { data, error, loading, reload } = useAsync(() => api<Page<Customer>>(`/api/customers?page=${page}&size=15`), [page])
  const [form, setForm] = useState({ firstName: '', lastName: '', email: '', country: 'FR', segment: 'STANDARD' })
  const [formError, setFormError] = useState<string>()

  async function create(e: FormEvent) {
    e.preventDefault()
    setFormError(undefined)
    try {
      await api('/api/customers', { method: 'POST', json: form })
      setForm({ ...form, firstName: '', lastName: '', email: '' })
      reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not create the customer')
    }
  }

  async function remove(id: string) {
    if (!window.confirm('Delete this customer?')) return
    try {
      await api(`/api/customers/${id}`, { method: 'DELETE' })
      reload()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not delete')
    }
  }

  return (
    <>
      <div className="page-head"><h1>Customers</h1><button onClick={reload}>Refresh</button></div>
      <ErrorNote error={error ?? formError} />
      <Card>
        {loading && !data ? <Loading what="customers" /> : (
          <table>
            <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Country</th><th>Segment</th><th>Created</th>{isAdmin && <th />}</tr></thead>
            <tbody>
              {data?.content.map((c) => (
                <tr key={c.id}>
                  <td title={c.id}>{shortId(c.id)}</td><td>{c.firstName} {c.lastName}</td><td>{c.email}</td>
                  <td>{c.country}</td><td>{c.segment}</td><td>{when(c.createdAt)}</td>
                  {isAdmin && <td><button className="link bad" onClick={() => remove(c.id)}>Delete</button></td>}
                </tr>
              ))}
              {data?.content.length === 0 && <tr><td colSpan={7} className="muted center">No customers.</td></tr>}
            </tbody>
          </table>
        )}
        <Pager page={page} totalPages={data?.totalPages ?? 0} onPage={setPage} />
      </Card>
      <Card title="Create a customer">
        <form onSubmit={create} className="form">
          <label>First name<input required maxLength={100} value={form.firstName} onChange={(e) => setForm({ ...form, firstName: e.target.value })} /></label>
          <label>Last name<input required maxLength={100} value={form.lastName} onChange={(e) => setForm({ ...form, lastName: e.target.value })} /></label>
          <label>Email<input type="email" required maxLength={254} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Country (ISO-2)<input required pattern="[A-Z]{2}" maxLength={2} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })} /></label>
          <label>Segment
            <select value={form.segment} onChange={(e) => setForm({ ...form, segment: e.target.value })}><option>STANDARD</option><option>PREMIUM</option></select>
          </label>
          <div className="row"><button type="submit">Create</button></div>
        </form>
      </Card>
    </>
  )
}
