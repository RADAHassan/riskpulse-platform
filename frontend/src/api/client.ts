import type { TokenResponse } from './types'

/** API base URL: empty = same origin (nginx / Vite dev proxy forward /api to the gateway). */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

const REFRESH_KEY = 'rp.refresh'

export class ApiError extends Error {
  readonly status: number
  readonly errors: string[]

  constructor(status: number, message: string, errors: string[] = []) {
    super(message)
    this.status = status
    this.errors = errors
  }
}

type Listener = (user: TokenResponse | null) => void

/**
 * Token store. The access token (15 min) lives in memory only; the refresh token is kept in sessionStorage
 * so a page reload keeps the session but closing the tab ends it. Refresh tokens rotate on every use.
 */
export const session = {
  accessToken: null as string | null,
  user: null as TokenResponse | null,
  listeners: new Set<Listener>(),
  refreshing: null as Promise<boolean> | null,

  get refreshToken(): string | null {
    return sessionStorage.getItem(REFRESH_KEY)
  },
  set(tokens: TokenResponse) {
    this.accessToken = tokens.accessToken
    this.user = tokens
    sessionStorage.setItem(REFRESH_KEY, tokens.refreshToken)
    this.listeners.forEach((l) => l(tokens))
  },
  clear() {
    this.accessToken = null
    this.user = null
    sessionStorage.removeItem(REFRESH_KEY)
    this.listeners.forEach((l) => l(null))
  },
  subscribe(listener: Listener) {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  },
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText || `HTTP ${res.status}`
  let errors: string[] = []
  try {
    const body = await res.json()
    detail = body.detail ?? body.title ?? detail
    errors = Array.isArray(body.errors) ? body.errors : []
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, detail, errors)
}

async function rawFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}

/** Single-flight refresh: concurrent 401s share one rotation of the refresh token. */
export function refreshSession(): Promise<boolean> {
  if (session.refreshing) return session.refreshing
  const refreshToken = session.refreshToken
  if (!refreshToken) return Promise.resolve(false)
  session.refreshing = (async () => {
    try {
      const res = await rawFetch('/api/auth/refresh', { method: 'POST', body: JSON.stringify({ refreshToken }) }, null)
      if (!res.ok) {
        session.clear()
        return false
      }
      session.set((await res.json()) as TokenResponse)
      return true
    } catch {
      session.clear()
      return false
    } finally {
      session.refreshing = null
    }
  })()
  return session.refreshing
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init
  const options: RequestInit = { ...rest, body: json !== undefined ? JSON.stringify(json) : rest.body }
  let res = await rawFetch(path, options, session.accessToken)
  if (res.status === 401 && session.refreshToken && (await refreshSession())) {
    res = await rawFetch(path, options, session.accessToken)
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** Fetch a binary resource (figures) with the bearer token and return an object URL. */
export async function apiBlobUrl(path: string): Promise<string> {
  let res = await rawFetch(path, {}, session.accessToken)
  if (res.status === 401 && (await refreshSession())) res = await rawFetch(path, {}, session.accessToken)
  if (!res.ok) throw await parseError(res)
  return URL.createObjectURL(await res.blob())
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const res = await rawFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }, null)
  if (!res.ok) throw await parseError(res)
  const tokens = (await res.json()) as TokenResponse
  session.set(tokens)
  return tokens
}

export async function logout(): Promise<void> {
  const refreshToken = session.refreshToken
  try {
    if (refreshToken) {
      await rawFetch('/api/auth/logout', { method: 'POST', body: JSON.stringify({ refreshToken }) }, null)
    }
  } finally {
    session.clear()
  }
}

/** Restore a session after a page reload using the refresh token. */
export async function restoreSession(): Promise<boolean> {
  return session.refreshToken ? refreshSession() : false
}
