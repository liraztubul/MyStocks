import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getMe, login, register, type Credentials } from '../api/auth'
import { ApiError } from '../api/client'

const ME_KEY = ['auth', 'me']

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: getMe,
    // A 401 is an answer ("logged out"), not a transient failure worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 401) && failureCount < 3,
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: login,
    onSuccess: (user) => queryClient.setQueryData(ME_KEY, user),
  })
}

// Register doesn't set the cookie, so log straight in afterwards for a one-step signup.
export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (credentials: Credentials) => {
      await register(credentials)
      return login(credentials)
    },
    onSuccess: (user) => queryClient.setQueryData(ME_KEY, user),
  })
}
