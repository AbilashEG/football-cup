"use client"

import { useState } from "react"
import AgentCard from "./AgentCard"
import FormationPicker from "./FormationPicker"
import { AgentConfig, PlayerRole, SquadConfig } from "@/types/agent.types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

const DEFAULT_AGENTS: AgentConfig[] = [
  {
    player_id: "GK_01",
    role: "GOALKEEPER" as PlayerRole,
    system_prompt:
      "You are GK_01, the GOALKEEPER. Protect the left goal (x=-29). " +
      "GOALKEEPER_DIVE when shot is incoming. CLEAR in penalty box. PASS to defenders.",
  },
  {
    player_id: "DEF_L",
    role: "DEFENDER" as PlayerRole,
    system_prompt:
      "You are DEF_L, the LEFT DEFENDER. Stay between ball and goal. " +
      "MARK the striker. TACKLE when adjacent. PASS to MID_01 when you have possession.",
  },
  {
    player_id: "DEF_R",
    role: "DEFENDER" as PlayerRole,
    system_prompt:
      "You are DEF_R, the RIGHT DEFENDER. Mirror DEF_L on the right side. " +
      "Cover right flank. INTERCEPT passing lanes. CLEAR under pressure.",
  },
  {
    player_id: "MID_01",
    role: "MIDFIELDER" as PlayerRole,
    system_prompt:
      "You are MID_01, the MIDFIELDER. Link defence to attack. " +
      "PASS to STR_01 when forward channel is clear. PRESS_BALL in midfield. " +
      "DRIBBLE only when space is open.",
  },
  {
    player_id: "STR_01",
    role: "STRIKER" as PlayerRole,
    system_prompt:
      "You are STR_01, the STRIKER. Score goals. " +
      "SHOOT when angle > 20 degrees and distance < 15. " +
      "MOVE_TO behind defensive line to receive passes. Never track back past halfway.",
  },
]

export default function SquadBuilder() {
  const [squadName, setSquadName] = useState("My Squad")
  const [teamColor, setTeamColor] = useState("#00D4FF")
  const [formation, setFormation] =
    useState<SquadConfig["formation"]>("4-1")
  const [agents, setAgents] = useState<AgentConfig[]>(DEFAULT_AGENTS)
  const [saving, setSaving] = useState(false)
  const [savedId, setSavedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function handleAgentChange(index: number, updated: AgentConfig) {
    setAgents((prev) => prev.map((a, i) => (i === index ? updated : a)))
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${API_URL}squad/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          squad_name: squadName,
          team_color: teamColor,
          formation,
          agents,
        } satisfies Omit<SquadConfig, "squad_id">),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSavedId(data.squad_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      {/* Squad metadata */}
      <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#F0F4FF] mb-4 uppercase tracking-wider">
          Squad Configuration
        </h2>
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
              Squad Name
            </label>
            <input
              value={squadName}
              onChange={(e) => setSquadName(e.target.value)}
              maxLength={60}
              className="bg-[#0A1628] border border-[rgba(0,212,255,0.2)] rounded px-3 py-1.5
                         text-sm text-[#F0F4FF] focus:outline-none focus:border-[#00D4FF] w-56"
            />
          </div>
          <div>
            <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
              Team Colour
            </label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={teamColor}
                onChange={(e) => setTeamColor(e.target.value)}
                className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent"
              />
              <span className="text-xs font-mono text-[#6B7FA3]">{teamColor}</span>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            {savedId && (
              <span className="text-xs text-[#00FF87] font-mono">
                ✓ Saved — {savedId}
              </span>
            )}
            {error && (
              <span className="text-xs text-[#FF3D57]">{error}</span>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2 bg-[#FF9900] hover:bg-[#e68a00] disabled:opacity-50
                         text-black font-bold text-sm rounded transition-colors"
            >
              {saving ? "Saving..." : "Save Squad"}
            </button>
          </div>
        </div>
      </div>

      {/* Formation picker */}
      <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#F0F4FF] mb-4 uppercase tracking-wider">
          Formation
        </h2>
        <FormationPicker
          formation={formation}
          onChange={setFormation}
          teamColor={teamColor}
        />
      </div>

      {/* Agent cards */}
      <div>
        <h2 className="text-sm font-bold text-[#F0F4FF] mb-3 uppercase tracking-wider">
          Agent System Prompts
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {agents.map((agent, i) => (
            <AgentCard
              key={agent.player_id}
              agent={agent}
              onChange={(updated) => handleAgentChange(i, updated)}
              index={i}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
