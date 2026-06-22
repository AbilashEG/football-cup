"use client"

import { useEffect, useRef } from "react"
import { TickEvent, ROLE_COLORS, COMMAND_COLORS, ROLE_LABELS } from "@/types/agent.types"

interface AgentFeedProps {
  feed: TickEvent[]
}

const ROLE_MAP: Record<string, string> = {
  GK_01:  "GOALKEEPER",
  DEF_L:  "DEFENDER",
  DEF_R:  "DEFENDER",
  MID_01: "MIDFIELDER",
  STR_01: "STRIKER",
}

function FeedLine({ event }: { event: TickEvent }) {
  const role = ROLE_MAP[event.player_id] as keyof typeof ROLE_COLORS | undefined
  const roleColor = role ? ROLE_COLORS[role] : "#6B7FA3"
  const cmdColor = COMMAND_COLORS[event.command.type] ?? "#6B7FA3"
  const roleLabel = role ? ROLE_LABELS[role] : "???"
  const latencyColor =
    event.latency_ms > 800 ? "#FF3D57" :
    event.latency_ms > 600 ? "#FF9900" : "#00FF87"

  return (
    <div
      className="flex items-start gap-2 px-3 py-1.5 border-b border-[rgba(0,212,255,0.08)]
                 hover:bg-[rgba(0,212,255,0.04)] transition-colors duration-100"
    >
      {/* Tick */}
      <span className="text-[10px] text-[#3D4F6B] w-8 shrink-0 pt-0.5 font-mono">
        T{event.tick}
      </span>

      {/* Role badge */}
      <span
        className="text-[9px] font-bold px-1 py-0.5 rounded shrink-0"
        style={{ color: roleColor, backgroundColor: `${roleColor}18` }}
      >
        {roleLabel}
      </span>

      {/* Player ID */}
      <span className="text-[11px] text-[#6B7FA3] shrink-0 font-mono w-14">
        {event.player_id}
      </span>

      {/* Command */}
      <span
        className="text-[11px] font-bold shrink-0 w-28 font-mono"
        style={{ color: cmdColor }}
      >
        {event.command.type}
      </span>

      {/* Rationale */}
      <span className="text-[11px] text-[#8090A8] flex-1 leading-tight truncate">
        {event.command.rationale}
      </span>

      {/* Latency */}
      <span
        className="text-[10px] font-mono shrink-0"
        style={{ color: latencyColor }}
      >
        {event.latency_ms.toFixed(0)}ms
      </span>
    </div>
  )
}

export default function AgentFeed({ feed }: AgentFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to top on new events (newest first)
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0
    }
  }, [feed.length])

  return (
    <div className="flex flex-col h-full bg-[#0D1B2A] rounded-lg border border-[rgba(0,212,255,0.15)]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[rgba(0,212,255,0.15)]">
        <span className="text-xs font-semibold text-[#00D4FF] tracking-wider uppercase">
          Agent Decision Feed
        </span>
        <span className="text-[10px] text-[#6B7FA3] font-mono">
          {feed.length} events
        </span>
      </div>

      {/* Scrollable terminal */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto"
        style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}
      >
        {feed.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#3D4F6B] text-sm">
            Waiting for match to start...
          </div>
        ) : (
          feed.map((event, i) => (
            <FeedLine key={`${event.tick}-${event.player_id}-${i}`} event={event} />
          ))
        )}
      </div>
    </div>
  )
}
