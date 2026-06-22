"use client"

import { ViewMode } from "@/types/agent.types"

interface NavBarProps {
  view: ViewMode
  onViewChange: (v: ViewMode) => void
  matchPhase?: string
}

const NAV_ITEMS: { id: ViewMode; label: string; icon: string }[] = [
  { id: "squad",    label: "Squad",    icon: "⚙" },
  { id: "match",    label: "Match",    icon: "⚽" },
  { id: "strategy", label: "Strategy", icon: "📋" },
  { id: "stack",    label: "Stack",    icon: "☁" },
]

const PHASE_COLORS: Record<string, string> = {
  FIRST_HALF:  "#00FF87",
  SECOND_HALF: "#00FF87",
  HALF_TIME:   "#FF9900",
  FULL_TIME:   "#FF3D57",
  PRE_MATCH:   "#6B7FA3",
}

export default function NavBar({ view, onViewChange, matchPhase }: NavBarProps) {
  const isLive =
    matchPhase === "FIRST_HALF" || matchPhase === "SECOND_HALF"
  const phaseColor = matchPhase ? (PHASE_COLORS[matchPhase] ?? "#6B7FA3") : undefined

  return (
    <nav className="flex items-center justify-between h-14 px-6 bg-[#0D1B2A] border-b border-[rgba(0,212,255,0.15)]">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <span className="text-xl">⚽</span>
        <div>
          <span className="text-sm font-bold text-[#F0F4FF] tracking-tight">
            Football Cup
          </span>
          <span className="text-[10px] text-[#6B7FA3] ml-2 font-mono">
            AWS AgentCore
          </span>
        </div>
      </div>

      {/* Nav items */}
      <div className="flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const active = view === item.id
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={[
                "flex items-center gap-2 px-4 py-1.5 rounded text-sm font-medium transition-all duration-150",
                active
                  ? "bg-[rgba(0,212,255,0.12)] text-[#00D4FF] border border-[rgba(0,212,255,0.25)]"
                  : "text-[#6B7FA3] hover:text-[#F0F4FF] hover:bg-[rgba(255,255,255,0.05)]",
              ].join(" ")}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          )
        })}
      </div>

      {/* Right: LIVE badge + region */}
      <div className="flex items-center gap-3">
        {isLive && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[rgba(255,61,87,0.12)]
                          border border-[rgba(255,61,87,0.3)] rounded-full">
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ backgroundColor: "#FF3D57" }}
            />
            <span className="text-[10px] font-bold text-[#FF3D57] tracking-widest">
              LIVE
            </span>
          </div>
        )}
        {matchPhase && !isLive && (
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded"
            style={{
              color: phaseColor,
              backgroundColor: `${phaseColor}18`,
            }}
          >
            {matchPhase.replace("_", " ")}
          </span>
        )}
        <div className="text-[10px] text-[#3D4F6B] font-mono hidden sm:block">
          us-east-1 · Nova Micro
        </div>
      </div>
    </nav>
  )
}
