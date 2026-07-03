import { useQuery } from '@tanstack/react-query'

import { getConfig } from './api'

/**
 * Whether a deployment feature flag is enabled (from GET /config, driven by
 * the backend's RANKFORGE_FEATURES env var). Returns false while loading or
 * on error, so flagged UI simply stays hidden on a stock install.
 */
export function useFeature(name: string): boolean {
  const { data } = useQuery({
    queryKey: ['appConfig'],
    queryFn: getConfig,
    staleTime: Infinity,
    retry: 1,
  })
  return data?.features.includes(name) ?? false
}
