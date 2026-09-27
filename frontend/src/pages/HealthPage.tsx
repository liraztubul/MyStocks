import { useHealth } from '../hooks/useHealth'

export function HealthPage() {
  const { data, error, isPending } = useHealth()

  let status: string
  if (isPending) status = 'checking…'
  else if (error) status = `unreachable (${error.message})`
  else status = data.status

  return (
    <main>
      <h1>MyStocks</h1>
      <p>
        Backend status: <strong data-testid="health-status">{status}</strong>
      </p>
    </main>
  )
}
