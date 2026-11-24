import { useCallback, useEffect, useRef, useState } from 'react'

interface State<T> {
  key: string
  data?: T
  error?: string
}

/** Small data-loading hook: `loading` is derived from the request key, so no state is set synchronously in effects. */
export function useAsync<T>(fn: () => Promise<T>, deps: ReadonlyArray<unknown>) {
  const [tick, setTick] = useState(0)
  const [state, setState] = useState<State<T>>({ key: '' })
  const latest = useRef(fn)
  const key = `${JSON.stringify(deps)}#${tick}`

  useEffect(() => {
    latest.current = fn
  })

  useEffect(() => {
    let cancelled = false
    latest
      .current()
      .then((data) => {
        if (!cancelled) setState({ key, data })
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ key, error: e instanceof Error ? e.message : 'Request failed' })
      })
    return () => {
      cancelled = true
    }
  }, [key])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const settled = state.key === key
  return { data: state.data, error: settled ? state.error : undefined, loading: !settled, reload }
}
