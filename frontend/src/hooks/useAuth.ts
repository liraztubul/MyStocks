import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { getMe, login, register, type Registration, type User } from '../api/auth'
import { ApiError } from '../api/client'

const ME_KEY = ['auth', 'me']
// Why the login page is showing, when it wasn't the user's choice. Lives in the query cache only
// so it can be shared without a separate store.
const SESSION_NOTICE_KEY = ['auth', 'notice']

export type SessionNotice = 'expired' | null

// A 401 from /me is an answer ("logged out"), so it's data (null), not an error. That matters:
// TanStack resets a query with no data to `pending` on every refetch, and the focus refetch would
// then swap the login page for the boot screen and wipe a half-filled form. With null as data, a
// refetch only runs in the background. Like returning Optional.empty() instead of throwing
// NotFound: absence is a normal result, and only real failures take the exception path.
async function getMeOrNull(): Promise<User | null> {
  try {
    return await getMe()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function useMe() {
  return useQuery<User | null>({
    queryKey: ME_KEY,
    queryFn: getMeOrNull,
    // Tab switches still re-check the session (a login in another tab, or an expiry, shows up
    // when you come back), but at most every 30 s rather than on every focus.
    staleTime: 30_000,
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: login,
    onSuccess: (user) => {
      queryClient.setQueryData(SESSION_NOTICE_KEY, null)
      queryClient.setQueryData(ME_KEY, user)
    },
  })
}

export function useSessionNotice(): SessionNotice {
  const { data } = useQuery<SessionNotice>({
    queryKey: SESSION_NOTICE_KEY,
    queryFn: () => null,
    enabled: false,
    initialData: null,
  })
  return data
}

// A 401 from a write means the session cookie expired mid-visit. Drop every cached ledger view
// (another account may log in next) and swap to the login page with a notice.
export function useExpireSession() {
  const queryClient = useQueryClient()
  return useCallback(() => {
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
    queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, 'expired')
    queryClient.setQueryData(ME_KEY, null)
  }, [queryClient])
}

// Register doesn't set the cookie, so log straight in afterwards for a one-step signup.
export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (registration: Registration) => {
      await register(registration)
      return login({ email: registration.email, password: registration.password })
    },
    onSuccess: (user) => queryClient.setQueryData(ME_KEY, user),
  })
}
