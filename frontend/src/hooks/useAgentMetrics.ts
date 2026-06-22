"use client"

import { useState, useEffect, useCallback } from "react"
import { MatchStats } from "@/types/agent.types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""
const POLL_INTERVAL_MS = 5000

export function useAgentMetrics(matchId: string | null) {
  const [stats, setStats] = useState<MatchStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchStats = useCallback(async () => {
    if (!matchId || !API_URL) return
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}match/${matchId}/stats`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as MatchStats
      setStats(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [matchId])

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchStats])

  return { stats, loading, error, refetch: fetchStats }
}
