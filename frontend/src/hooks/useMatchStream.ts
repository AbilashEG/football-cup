"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { GameState, TickEvent, ConnectionStatus } from "@/types/agent.types"

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? ""
const RECONNECT_DELAY_MS = 2000
const MAX_FEED_ITEMS = 50

export function useMatchStream(matchId: string | null) {
  const [gameState, setGameState] = useState<GameState | null>(null)
  const [agentFeed, setAgentFeed] = useState<TickEvent[]>([])
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected")
  const [lastTickMs, setLastTickMs] = useState<number>(0)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const clearReconnect = () => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current)
      reconnectRef.current = null
    }
  }

  const connect = useCallback(() => {
    if (!matchId || !WS_URL || !mountedRef.current) return

    // Clean up any existing connection first
    wsRef.current?.close()

    setConnectionStatus("connecting")

    const url = `${WS_URL}?matchId=${encodeURIComponent(matchId)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setConnectionStatus("connected")
      clearReconnect()
    }

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return
      try {
        const data = JSON.parse(event.data as string) as {
          type: "game_state" | "tick_event"
          payload: GameState | TickEvent
        }

        if (data.type === "game_state") {
          setGameState(data.payload as GameState)
          setLastTickMs(Date.now())
        } else if (data.type === "tick_event") {
          setAgentFeed((prev) => [
            data.payload as TickEvent,
            ...prev.slice(0, MAX_FEED_ITEMS - 1),
          ])
        }
      } catch {
        // Malformed JSON — ignore
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnectionStatus("disconnected")
      // Auto-reconnect unless match is over
      reconnectRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
    }

    ws.onerror = () => {
      // onerror always fires before onclose — just close the socket
      ws.close()
    }
  }, [matchId])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      clearReconnect()
      wsRef.current?.close()
    }
  }, [connect])

  const sendCoachHint = useCallback(
    (hint: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN && matchId) {
        wsRef.current.send(
          JSON.stringify({ type: "coach_hint", matchId, hint })
        )
      }
    },
    [matchId]
  )

  return {
    gameState,
    agentFeed,
    connectionStatus,
    lastTickMs,
    sendCoachHint,
  }
}
