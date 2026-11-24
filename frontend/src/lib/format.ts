export const shortId = (id: string | null | undefined): string => (id ? `${id.slice(0, 8)}…` : '—')

export const money = (amount: number, currency = 'EUR'): string =>
  new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(amount)

export const pct = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)} %`

export const num = (value: number | null | undefined, digits = 4): string =>
  value === null || value === undefined ? '—' : value.toFixed(digits)

export const when = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'medium' }) : '—'

/** Parses "0.1, -2.3 ..." (commas, spaces, newlines or a JSON array) into numbers; throws on anything non numeric. */
export function parseFeatures(text: string): number[] {
  const cleaned = text.trim().replace(/^\[/, '').replace(/\]$/, '')
  if (!cleaned) return []
  return cleaned.split(/[\s,;]+/).filter(Boolean).map((token) => {
    const value = Number(token)
    if (!Number.isFinite(value)) throw new Error(`"${token}" is not a finite number`)
    return value
  })
}
