import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, login, logout, session } from './client'
import type { TokenResponse } from './types'

const tokens = (access: string, refresh = 'r1'): TokenResponse => ({
  accessToken: access, refreshToken: refresh, tokenType: 'Bearer', expiresIn: 900, username: 'admin', role: 'ADMIN', customerId: null,
})
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('api client', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    session.clear()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('logs in, keeps the access token in memory and the refresh token in sessionStorage', async () => {
    fetchMock.mockResolvedValueOnce(json(200, tokens('a1', 'r1')))
    await login('admin', 'pw')
    expect(session.accessToken).toBe('a1')
    expect(sessionStorage.getItem('rp.refresh')).toBe('r1')
    expect(localStorage.length).toBe(0)
  })

  it('sends the bearer token', async () => {
    session.set(tokens('a1'))
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }))
    await api('/api/customers')
    const headers = fetchMock.mock.calls[0][1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer a1')
  })

  it('refreshes once on 401 and replays the request with the new token', async () => {
    session.set(tokens('old', 'r-old'))
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(200, tokens('new', 'r-new')))
      .mockResolvedValueOnce(json(200, { value: 42 }))
    const result = await api<{ value: number }>('/api/transactions')
    expect(result.value).toBe(42)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/refresh')
    expect((fetchMock.mock.calls[2][1].headers as Headers).get('Authorization')).toBe('Bearer new')
    expect(sessionStorage.getItem('rp.refresh')).toBe('r-new') // rotated
  })

  it('shares one refresh between concurrent 401s', async () => {
    session.set(tokens('old', 'r-old'))
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (url === '/api/auth/refresh') return json(200, tokens('new', 'r-new'))
      return (init.headers as Headers).get('Authorization') === 'Bearer new' ? json(200, {}) : json(401, {})
    })
    await Promise.all([api('/api/a'), api('/api/b'), api('/api/c')])
    expect(fetchMock.mock.calls.filter((c) => c[0] === '/api/auth/refresh')).toHaveLength(1)
  })

  it('clears the session when the refresh token is rejected', async () => {
    session.set(tokens('old', 'r-old'))
    fetchMock.mockResolvedValueOnce(json(401, {})).mockResolvedValueOnce(json(401, {}))
    await expect(api('/api/transactions')).rejects.toMatchObject({ status: 401 })
    expect(session.accessToken).toBeNull()
    expect(sessionStorage.getItem('rp.refresh')).toBeNull()
  })

  it('maps RFC 7807 problems to ApiError', async () => {
    session.set(tokens('a'))
    fetchMock.mockResolvedValueOnce(json(400, { title: 'Bad Request', detail: 'Validation failed', errors: ['amount: must be >= 0'] }))
    const error = (await api('/api/transactions', { method: 'POST', json: {} }).catch((e) => e)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(400)
    expect(error.errors).toEqual(['amount: must be >= 0'])
  })

  it('revokes the refresh token on logout', async () => {
    session.set(tokens('a', 'r9'))
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await logout()
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ refreshToken: 'r9' })
    expect(session.accessToken).toBeNull()
  })
})
