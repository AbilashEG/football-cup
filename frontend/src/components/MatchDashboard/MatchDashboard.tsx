"use client"

import { useState } from "react"
import dynamic from "next/dynamic"
import AgentFeed from "./AgentFeed"
import MatchStats from "./MatchStats"
import { useMatchStream } from "@/hooks/useMatchStream"
import { useAgentMetrics } from "@/hooks/useAgentMetrics"

// PitchCanvas uses Three.js — must be client-side only, no SSR
const PitchCanvas = dynamic(() => import("./PitchCanvas"), { ssr: false })

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

interface MatchDashboardProps {
  initialMatchId?: string
}

export default function MatchDashboard({ initialMatchId }: MatchDashboardProps) {
  const [matchId, setMatchId] = useState<string | null>(initialMatchId ?? null)
  const [teamAName, setTeamAName] = useState("Crimson Rovers")
  const [teamBName, setTeamBName] = useState("Azure FC")
  const [starting, setStarting] = useState(false)
  const [hintText, setHintText] = useState("")

  const { gameState, agentFeed, connectionStatus, sendCoachHint } =
    useMatchStream(matchId)
  const { stats } = useAgentMetrics(matchId)

  const teamAId = gameState?.scores?.[0]?.team_id

  const statusColor = {
    connecting:   "#FF9900",
    connected:    "#00FF87",
    disconnected: "#FF3D57",
  }[connectionStatus]

  async function handleStartMatch() {
    setStarting(true)
    try {
      const res = await fetch(`${API_URL}match/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          team_a: { team_id: "team_a", team_name: teamAName },
          team_b: { team_id: "team_b", team_name: teamBName },
        }),
      })
      const data = await res.json()
      setMatchId(data.match_id)
    } catch (e) {
      console.error("Start match error:", e)
    } finally {
      setStarting(false)
    }
  }

  function handleSendHint() {
    if (!hintText.trim()) return
    sendCoachHint(hintText.trim())
    setHintText("")
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Top bar: match controls */}
      {!matchId ? (
        <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-4">
          <div className="flex items-end gap-3 flex-wrap">
            <div>
              <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
                Team A
              </label>
              <input
                className="bg-[#0A1628] border border-[rgba(0,212,255,0.2)] rounded px-3 py-1.5
                           text-sm text-[#F0F4FF] focus:outline-none focus:border-[#00D4FF]"
                value={teamAName}
                onChange={e => setTeamAName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
                Team B
              </label>
              <input
                className="bg-[#0A1628] border border-[rgba(0,212,255,0.2)] rounded px-3 py-1.5
                           text-sm text-[#F0F4FF] focus:outline-none focus:border-[#FF9900]"
                value={teamBName}
                onChange={e => setTeamBName(e.target.value)}
              />
            </div>
            <button
              onClick={handleStartMatch}
              disabled={starting}
              className="px-6 py-2 bg-[#FF9900] hover:bg-[#e68a00] disabled:opacity-50
                         text-black font-bold text-sm rounded transition-colors"
            >
              {starting ? "Starting..." : "⚽ Kick Off"}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg px-4 py-2">
          <div className="flex items-center gap-3">
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: statusColor }}
            />
            <span className="text-xs text-[#6B7FA3] font-mono">
              {connectionStatus.toUpperCase()} — Match{" "}
              <span className="text-[#00D4FF]">{matchId}</span>
            </span>
          </div>
          {/* Coach hint input */}
          <div className="flex gap-2">
            <input
              className="bg-[#0A1628] border border-[rgba(0,212,255,0.2)] rounded px-3 py-1
                         text-sm text-[#F0F4FF] w-64 focus:outline-none focus:border-[#00D4FF]
                         placeholder-[#3D4F6B]"
              placeholder="Coach hint (e.g. press higher)..."
              value={hintText}
              onChange={e => setHintText(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSendHint()}
              maxLength={200}
            />
            <button
              onClick={handleSendHint}
              disabled={!hintText.trim()}
              className="px-3 py-1 bg-[#0F2035] hover:bg-[#1A3050] border border-[rgba(0,212,255,0.25)]
                         text-[#00D4FF] text-xs rounded transition-colors disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      )}

      {/* Main grid: pitch + feed + stats */}
      <div className="flex-1 grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4 min-h-0">
        {/* Left: pitch + stats */}
        <div className="flex flex-col gap-4">
          <div className="rounded-lg overflow-hidden border border-[rgba(0,212,255,0.12)]">
            <PitchCanvas gameState={gameState} teamAId={teamAId} />
          </div>
          <MatchStats gameState={gameState} stats={stats} />
        </div>

        {/* Right: agent feed */}
        <div className="min-h-0 h-[640px] xl:h-auto">
          <AgentFeed feed={agentFeed} />
        </div>
      </div>
    </div>
  )
}
