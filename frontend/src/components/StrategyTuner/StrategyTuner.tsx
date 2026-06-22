"use client"

import { useState, useEffect } from "react"
import { ROLE_COLORS, PlayerRole } from "@/types/agent.types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

interface MatchHistoryItem {
  match_id: string
  completed_at: string
  winner: string
  scores: { team_name: string; goals: number }[]
}

interface PlayerDecision {
  tick: number
  command_type: string
  rationale: string
  latency_ms: number
}

const ROLE_MAP: Record<string, PlayerRole> = {
  GK_01:  "GOALKEEPER",
  DEF_L:  "DEFENDER",
  DEF_R:  "DEFENDER",
  MID_01: "MIDFIELDER",
  STR_01: "STRIKER",
}

const PLAYER_IDS = ["GK_01", "DEF_L", "DEF_R", "MID_01", "STR_01"]

export default function StrategyTuner() {
  const [selectedMatchId, setSelectedMatchId] = useState<string>("")
  const [selectedPlayer, setSelectedPlayer] = useState<string>("STR_01")
  const [decisions, setDecisions] = useState<PlayerDecision[]>([])
  const [history, setHistory] = useState<MatchHistoryItem[]>([])
  const [loadingDecisions, setLoadingDecisions] = useState(false)
  const [promptDraft, setPromptDraft] = useState("")
  const [applyStatus, setApplyStatus] = useState<string | null>(null)

  // Load dummy match history (would come from /replay list in production)
  useEffect(() => {
    setHistory([
      {
        match_id: "DEMO01",
        completed_at: new Date().toISOString(),
        winner: "Crimson Rovers",
        scores: [{ team_name: "Crimson Rovers", goals: 3 }, { team_name: "Azure FC", goals: 1 }],
      },
    ])
  }, [])

  async function loadDecisions() {
    if (!selectedMatchId || !selectedPlayer) return
    setLoadingDecisions(true)
    try {
      const res = await fetch(
        `${API_URL}replay/${selectedMatchId}/player/${selectedPlayer}`
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setDecisions(data.decisions ?? [])
    } catch {
      setDecisions([])
    } finally {
      setLoadingDecisions(false)
    }
  }

  function handleApplyAndRedeploy() {
    setApplyStatus("Prompt saved. Redeploy agent to apply changes.")
    setTimeout(() => setApplyStatus(null), 4000)
  }

  const role = ROLE_MAP[selectedPlayer]
  const roleColor = role ? ROLE_COLORS[role] : "#6B7FA3"

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#F0F4FF] mb-1 uppercase tracking-wider">
          Strategy Tuner
        </h2>
        <p className="text-[11px] text-[#6B7FA3] mb-4">
          Review agent decisions from past matches, edit system prompts, and redeploy.
        </p>

        {/* Controls */}
        <div className="flex flex-wrap gap-3 items-end mb-4">
          <div>
            <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
              Match ID
            </label>
            <input
              value={selectedMatchId}
              onChange={(e) => setSelectedMatchId(e.target.value.toUpperCase())}
              placeholder="e.g. DEMO01"
              className="bg-[#0A1628] border border-[rgba(0,212,255,0.2)] rounded px-3 py-1.5
                         text-sm text-[#F0F4FF] focus:outline-none focus:border-[#00D4FF] w-40 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
              Player
            </label>
            <select
              value={selectedPlayer}
              onChange={(e) => setSelectedPlayer(e.target.value)}
              className="bg-[#0A1628] border border-[rgba(0,212,255,0.2)] rounded px-3 py-1.5
                         text-sm text-[#F0F4FF] focus:outline-none focus:border-[#00D4FF]"
            >
              {PLAYER_IDS.map((pid) => (
                <option key={pid} value={pid}>{pid}</option>
              ))}
            </select>
          </div>
          <button
            onClick={loadDecisions}
            disabled={loadingDecisions || !selectedMatchId}
            className="px-4 py-1.5 border border-[rgba(0,212,255,0.25)] text-[#00D4FF] text-xs
                       rounded hover:bg-[rgba(0,212,255,0.08)] transition-colors disabled:opacity-40"
          >
            {loadingDecisions ? "Loading..." : "Load Decisions"}
          </button>
        </div>

        {/* Decision table */}
        {decisions.length > 0 && (
          <div className="bg-[#070F1A] rounded border border-[rgba(0,212,255,0.1)] overflow-hidden mb-4">
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-[rgba(0,212,255,0.1)]">
                    {["Tick", "Command", "Latency", "Rationale"].map((h) => (
                      <th key={h} className="text-left px-3 py-1.5 text-[#6B7FA3] font-normal uppercase tracking-wider text-[9px]">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((d, i) => (
                    <tr
                      key={i}
                      className="border-b border-[rgba(0,212,255,0.05)] hover:bg-[rgba(0,212,255,0.03)]"
                    >
                      <td className="px-3 py-1 font-mono text-[#6B7FA3]">{d.tick}</td>
                      <td className="px-3 py-1 font-mono font-bold" style={{ color: roleColor }}>
                        {d.command_type}
                      </td>
                      <td className="px-3 py-1 font-mono text-[#6B7FA3]">
                        {d.latency_ms.toFixed(0)}ms
                      </td>
                      <td className="px-3 py-1 text-[#8090A8] truncate max-w-xs">
                        {d.rationale}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Prompt editor */}
        <div>
          <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
            Edit System Prompt — {selectedPlayer}
          </label>
          <textarea
            value={promptDraft}
            onChange={(e) => setPromptDraft(e.target.value)}
            rows={6}
            maxLength={2000}
            placeholder={`Paste or type updated system prompt for ${selectedPlayer}...`}
            className="w-full bg-[#070F1A] border border-[rgba(0,212,255,0.12)] rounded px-3 py-2
                       text-[11px] text-[#C0CFDF] font-mono resize-none focus:outline-none
                       focus:border-[rgba(0,212,255,0.4)] leading-relaxed placeholder-[#3D4F6B]"
          />
          <div className="flex items-center justify-between mt-2">
            <span className="text-[9px] font-mono text-[#3D4F6B]">
              {promptDraft.length}/2000
            </span>
            <div className="flex items-center gap-3">
              {applyStatus && (
                <span className="text-xs text-[#00FF87]">{applyStatus}</span>
              )}
              <button
                onClick={handleApplyAndRedeploy}
                disabled={!promptDraft.trim()}
                className="px-4 py-1.5 bg-[#FF9900] hover:bg-[#e68a00] disabled:opacity-40
                           text-black font-bold text-xs rounded transition-colors"
              >
                Apply &amp; Redeploy
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Match history cards */}
      <div>
        <h3 className="text-xs font-bold text-[#F0F4FF] mb-3 uppercase tracking-wider">
          Match History
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {history.map((m) => (
            <button
              key={m.match_id}
              onClick={() => setSelectedMatchId(m.match_id)}
              className={[
                "text-left bg-[#0D1B2A] border rounded-lg p-4 transition-all",
                selectedMatchId === m.match_id
                  ? "border-[#00D4FF]"
                  : "border-[rgba(0,212,255,0.15)] hover:border-[rgba(0,212,255,0.3)]",
              ].join(" ")}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-mono font-bold text-[#00D4FF]">
                  {m.match_id}
                </span>
                <span className="text-[9px] text-[#3D4F6B] font-mono">
                  {new Date(m.completed_at).toLocaleDateString()}
                </span>
              </div>
              <div className="text-sm font-bold text-[#F0F4FF] mb-1">
                {m.scores.map((s) => `${s.team_name} ${s.goals}`).join(" — ")}
              </div>
              <div className="text-[10px] text-[#00FF87]">
                Winner: {m.winner}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
