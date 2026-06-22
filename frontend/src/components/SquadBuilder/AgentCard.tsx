"use client"

import { AgentConfig, PlayerRole, ROLE_COLORS, ROLE_LABELS } from "@/types/agent.types"

interface AgentCardProps {
  agent: AgentConfig
  onChange: (updated: AgentConfig) => void
  index: number
}

const STATUS_OPTIONS = ["ready", "deploying", "error"] as const
type AgentStatus = (typeof STATUS_OPTIONS)[number]

const STATUS_STYLES: Record<AgentStatus, { color: string; label: string }> = {
  ready:     { color: "#00FF87", label: "Ready" },
  deploying: { color: "#FF9900", label: "Deploying" },
  error:     { color: "#FF3D57", label: "Error" },
}

const ROLE_DESCRIPTIONS: Record<PlayerRole, string> = {
  GOALKEEPER: "Guards the left goal (x = -29). Dive, clear, distribute.",
  DEFENDER:   "Holds defensive shape. Mark, intercept, tackle, clear.",
  MIDFIELDER: "Engine of the team. Press, pass, link play.",
  STRIKER:    "Sole objective: score. Shoot early, run behind the line.",
}

export default function AgentCard({ agent, onChange, index }: AgentCardProps) {
  const roleColor = ROLE_COLORS[agent.role]
  const roleLabel = ROLE_LABELS[agent.role]

  return (
    <div
      className="bg-[#0F2035] border rounded-lg p-4 flex flex-col gap-3 transition-all duration-200
                 hover:border-[rgba(0,212,255,0.3)]"
      style={{ borderColor: `${roleColor}30` }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-bold px-2 py-0.5 rounded-full"
            style={{
              color: roleColor,
              backgroundColor: `${roleColor}20`,
              border: `1px solid ${roleColor}40`,
            }}
          >
            {roleLabel}
          </span>
          <span className="text-sm font-bold text-[#F0F4FF] font-mono">
            {agent.player_id}
          </span>
        </div>
        {/* Status badge */}
        <div className="flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: STATUS_STYLES.ready.color }}
          />
          <span
            className="text-[9px] font-mono"
            style={{ color: STATUS_STYLES.ready.color }}
          >
            {STATUS_STYLES.ready.label}
          </span>
        </div>
      </div>

      {/* Role description */}
      <p className="text-[11px] text-[#6B7FA3] leading-relaxed">
        {ROLE_DESCRIPTIONS[agent.role]}
      </p>

      {/* System prompt editor */}
      <div>
        <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
          System Prompt
        </label>
        <textarea
          value={agent.system_prompt}
          onChange={(e) => onChange({ ...agent, system_prompt: e.target.value })}
          rows={4}
          maxLength={2000}
          className="w-full bg-[#070F1A] border border-[rgba(0,212,255,0.12)] rounded px-3 py-2
                     text-[11px] text-[#C0CFDF] font-mono resize-none focus:outline-none
                     focus:border-[rgba(0,212,255,0.4)] leading-relaxed
                     placeholder-[#3D4F6B]"
          placeholder={`Describe ${agent.player_id}'s tactics and decision rules...`}
        />
        <div className="text-right text-[9px] text-[#3D4F6B] mt-0.5 font-mono">
          {agent.system_prompt.length}/2000
        </div>
      </div>

      {/* AgentCore endpoint (read-only) */}
      {agent.agentcore_endpoint && (
        <div>
          <label className="block text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
            AgentCore Endpoint
          </label>
          <div className="bg-[#070F1A] border border-[rgba(0,212,255,0.08)] rounded px-2 py-1.5
                          text-[9px] text-[#3D4F6B] font-mono truncate">
            {agent.agentcore_endpoint}
          </div>
        </div>
      )}
    </div>
  )
}
