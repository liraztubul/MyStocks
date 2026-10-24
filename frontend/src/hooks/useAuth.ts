import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'
import { getMe, login, logout, register, type Registration, type User } from '../api/auth'
import { ApiError } from '../api/client'
import { parseAuthMessage, sessionEnded, type AuthMessage } from '../api/session'

const ME_KEY = ['auth', 'me']
// Why the login page is showing. Lives in the query cache only so it can be shared without a
// separate store.
const SESSION_NOTICE_KEY = ['auth', 'notice']

// expired: a 401 mid-visit. logged_out: the user's choice. logout_failed: the user's choice, but
// the server never confirmed it, so the cookie may still work.
export type SessionNotice = 'expired' | 'logged_out' | 'logout_failed' | null

// One per tab: a channel object doesn't receive its own messages, so a tab never reacts to itself.
const authChannel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('mystocks-auth')

function tellOtherTabs(message: AuthMessage) {
  authChannel?.postMessage(message)
}

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
  const notice = useSessionNotice()
  return useQuery<User | null>({
    queryKey: ME_KEY,
    queryFn: getMeOrNull,
    // Tab switches still re-check the session (a login in another tab, or an expiry, shows up
    // when you come back), but at most every 30 s rather than on every focus.
    staleTime: 30_000,
    // After an explicit logout, asking /me again could silently log back in if the logout POST
    // hasn't landed yet. The next login (here or in another tab) clears the notice.
    enabled: notice !== 'logged_out' && notice !== 'logout_failed',
  })
}

function removePrivateQueries(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
}

function startSession(queryClient: QueryClient, user: User) {
  // Nothing from an earlier session (prices, stock history) carries over to this account.
  removePrivateQueries(queryClient)
  queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, null)
  queryClient.setQueryData(ME_KEY, user)
  tellOtherTabs('login')
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['auth', 'login'],
    mutationFn: login,
    onSuccess: (user) => startSession(queryClient, user),
  })
}

// Register doesn't set the cookie, so log straight in afterwards for a one-step signup.
export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['auth', 'register'],
    mutationFn: async (registration: Registration) => {
      await register(registration)
      return login({ email: registration.email, password: registration.password })
    },
    onSuccess: (user) => startSession(queryClient, user),
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

// A 401 mid-visit means the session cookie expired. Drop every cached private view (another
// account may log in next) and swap to the login page with a notice. Called by the query
// client for any non-auth 401 (main.tsx).
export function expireSession(queryClient: QueryClient) {
  removePrivateQueries(queryClient)
  // Already on the login page (e.g. a write that was in flight during a logout): keep its notice.
  if (queryClient.getQueryData(ME_KEY) === null) return
  queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, 'expired')
  queryClient.setQueryData(ME_KEY, null)
}

// Logged out, as far as this tab is concerned: the login page shows first (ME null unmounts every
// private page), then all cached data and pending writes go.
async function endSessionLocally(queryClient: QueryClient) {
  await queryClient.cancelQueries()
  queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, 'logged_out')
  queryClient.setQueryData(ME_KEY, null)
  removePrivateQueries(queryClient)
  queryClient.getMutationCache().clear()
}

async function confirmLogout(queryClient: QueryClient) {
  try {
    await logout()
  } catch {
    // Only if the user hasn't logged in again meanwhile.
    if (queryClient.getQueryData(SESSION_NOTICE_KEY) === 'logged_out') {
      queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, 'logout_failed')
    }
  }
}

// Clear this tab first, then ask the server to revoke the token: logging out never waits on a
// sleeping backend, and a failure shows on the login page with a way to try again.
export function useLogout() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return useCallback(async () => {
    tellOtherTabs('logout')
    await endSessionLocally(queryClient)
    // Replace, so Back doesn't return to the private page's URL.
    navigate('/', { replace: true })
    await confirmLogout(queryClient)
  }, [queryClient, navigate])
}

export function useRetryLogout() {
  const queryClient = useQueryClient()
  return useCallback(async () => {
    queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, 'logged_out')
    await confirmLogout(queryClient)
  }, [queryClient])
}

// Keeps this tab in step with the others, and drops cached data whenever /me stops returning the
// user it showed (an expiry noticed on focus, or a logout in a browser without BroadcastChannel).
export function useSessionSync(user: User | null | undefined) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const shown = useRef(user)

  useEffect(() => {
    if (sessionEnded(shown.current, user)) removePrivateQueries(queryClient)
    if (user !== undefined) shown.current = user
  }, [user, queryClient])

  useEffect(() => {
    if (!authChannel) return
    const channel = authChannel
    function onMessage(event: MessageEvent) {
      const message = parseAuthMessage(event.data)
      if (message === 'logout') {
        void endSessionLocally(queryClient).then(() => navigate('/', { replace: true }))
      } else if (message === 'login') {
        removePrivateQueries(queryClient)
        queryClient.setQueryData<SessionNotice>(SESSION_NOTICE_KEY, null)
        void queryClient.invalidateQueries({ queryKey: ME_KEY })
      }
    }
    channel.addEventListener('message', onMessage)
    return () => channel.removeEventListener('message', onMessage)
  }, [queryClient, navigate])
}
