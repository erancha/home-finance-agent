import { apiGet } from './client.ts'

export function getAgents(): Promise<{ agents: string[] }> {
  return apiGet('/api/agents')
}
