/** Loads the series list once for the picker. */

import { useEffect, useState } from 'react'
import { getSeries } from '../services/api'
import type { Series } from '../types'

/**
 * The indexed series (empty while loading or if the API is unreachable) and a load error.
 * Called by: App.tsx
 */
export function useSeries(): { series: Series[]; error: string | null } {
  const [series, setSeries] = useState<Series[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    getSeries()
      .then((list) => setSeries([...list].sort((a, b) => a.title.localeCompare(b.title))))
      .catch((err: Error) => setError(err.message))
  }, [])
  return { series, error }
}
