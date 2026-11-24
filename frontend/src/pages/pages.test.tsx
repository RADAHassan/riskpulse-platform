import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, session } from '../api/client'
import type { Page, ReviewCase, TokenResponse } from '../api/types'
import { AuthProvider } from '../auth/AuthContext'
import { ProtectedRoute } from '../auth/ProtectedRoute'
import { Login } from './Login'
import { Reviews } from './Reviews'

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return { ...actual, api: vi.fn(), login: vi.fn(), logout: vi.fn(), restoreSession: vi.fn(async () => false) }
})
import * as client from '../api/client'

const user = (role: TokenResponse['role']): TokenResponse => ({
  accessToken: 'a', refreshToken: 'r', tokenType: 'Bearer', expiresIn: 900, username: 'alice', role, customerId: null,
})

const reviewPage = (content: ReviewCase[]): Page<ReviewCase> => ({ content, page: 0, size: 10, totalElements: content.length, totalPages: 1 })
const openCase: ReviewCase = {
  id: 'case-1', transactionId: 'aaaaaaaa-1111-2222-3333-444444444444', customerId: 'c', amount: 250, probability: 0.61,
  uncertainty: 0.78, modelVersion: 'riskpulse-29d-v2.0-canonical', reason: 'uncertain_prediction_not_auto_declined',
  status: 'OPEN', resolvedBy: null, resolvedAt: null, note: null, createdAt: '2026-11-24T10:00:00Z',
}

beforeEach(() => {
  vi.mocked(client.api).mockReset()
  vi.mocked(client.login).mockReset()
  session.clear()
})

function renderAt(path: string, role?: TokenResponse['role']) {
  if (role) session.set(user(role))
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute><p>home</p></ProtectedRoute>} />
          <Route path="/reviews" element={<ProtectedRoute roles={['ADMIN', 'ANALYST']}><Reviews /></ProtectedRoute>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('authentication flow', () => {
  it('redirects anonymous users to the login page', () => {
    renderAt('/reviews')
    expect(screen.getByRole('form', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows a generic message on invalid credentials and does not reveal details', async () => {
    vi.mocked(client.login).mockRejectedValueOnce(new ApiError(401, 'Invalid credentials'))
    renderAt('/login')
    await userEvent.type(screen.getByLabelText('Username'), 'alice')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.')
  })

  it('tells the user when the account is locked', async () => {
    vi.mocked(client.login).mockRejectedValueOnce(new ApiError(423, 'locked'))
    renderAt('/login')
    await userEvent.type(screen.getByLabelText('Username'), 'alice')
    await userEvent.type(screen.getByLabelText('Password'), 'pw')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/temporarily locked/i)
  })

  it('keeps customers out of the staff-only review queue', () => {
    renderAt('/reviews', 'CUSTOMER')
    expect(screen.getByText('home')).toBeInTheDocument()
    expect(client.api).not.toHaveBeenCalled()
  })
})

describe('review queue', () => {
  it('lists open cases with probability, uncertainty and model version', async () => {
    vi.mocked(client.api).mockResolvedValueOnce(reviewPage([openCase]))
    renderAt('/reviews', 'ANALYST')
    const row = (await screen.findByText('aaaaaaaa…')).closest('tr')!
    expect(within(row).getByText('0.6100')).toBeInTheDocument()
    expect(within(row).getByText('0.780')).toBeInTheDocument()
    expect(within(row).getByText('riskpulse-29d-v2.0-canonical')).toBeInTheDocument()
  })

  it('approves a case with a note and reloads the queue', async () => {
    vi.mocked(client.api)
      .mockResolvedValueOnce(reviewPage([openCase]))
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce(reviewPage([]))
    renderAt('/reviews', 'ANALYST')
    await screen.findByText('aaaaaaaa…')
    await userEvent.type(screen.getByLabelText(/note for/i), 'customer confirmed by phone')
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(client.api).toHaveBeenCalledWith('/api/reviews/case-1/resolve', {
      method: 'POST', json: { resolution: 'APPROVE', note: 'customer confirmed by phone' },
    }))
    expect(await screen.findByText('Nothing to review.')).toBeInTheDocument()
  })

  it('rejects a case', async () => {
    vi.mocked(client.api).mockResolvedValueOnce(reviewPage([openCase])).mockResolvedValueOnce({}).mockResolvedValueOnce(reviewPage([]))
    renderAt('/reviews', 'ADMIN')
    await screen.findByText('aaaaaaaa…')
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(client.api).toHaveBeenCalledWith('/api/reviews/case-1/resolve', {
      method: 'POST', json: { resolution: 'REJECT', note: undefined },
    }))
  })

  it('surfaces API errors', async () => {
    vi.mocked(client.api).mockResolvedValueOnce(reviewPage([openCase])).mockRejectedValueOnce(new ApiError(409, 'Review case already resolved'))
    renderAt('/reviews', 'ANALYST')
    await screen.findByText('aaaaaaaa…')
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Review case already resolved')
  })
})
