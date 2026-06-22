"use client"

import { useEffect, useState } from "react"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

interface ServiceStatus {
  name: string
  status: "healthy" | "degraded" | "unknown"
  latencyMs?: number
  detail?: string
}

// SVG architecture flow nodes
const ARCH_NODES = [
  { id: "frontend",  label: "Next.js 14",        x: 340, y: 20,  color: "#00D4FF", icon: "⚛" },
  { id: "apigw",     label: "API Gateway",        x: 340, y: 90,  color: "#FF9900", icon: "⇌" },
  { id: "backend",   label: "FastAPI Lambda",      x: 340, y: 160, color: "#00FF87", icon: "λ" },
  { id: "agentcore", label: "AgentCore Runtime ×5",x: 560, y: 160, color: "#A78BFA", icon: "🤖" },
  { id: "nova",      label: "Nova Micro",          x: 700, y: 160, color: "#F472B6", icon: "✦" },
  { id: "dynamo",    label: "DynamoDB",            x: 200, y: 240, color: "#FF9900", icon: "⬡" },
  { id: "s3",        label: "S3 Events",           x: 340, y: 240, color: "#FF9900", icon: "🪣" },
  { id: "mcp",       label: "MCP Tools ×6",        x: 480, y: 240, color: "#00D4FF", icon: "🔧" },
]

const ARCH_EDGES = [
  ["frontend", "apigw"],
  ["apigw", "backend"],
  ["backend", "agentcore"],
  ["agentcore", "nova"],
  ["backend", "dynamo"],
  ["backend", "s3"],
  ["backend", "mcp"],
  ["mcp", "dynamo"],
  ["mcp", "s3"],
]

function getNodeCenter(id: string): [number, number] {
  const node = ARCH_NODES.find((n) => n.id === id)
  return node ? [node.x + 60, node.y + 18] : [0, 0]
}

export default function StackMonitor() {
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: "API Gateway",           status: "unknown" },
    { name: "FastAPI Lambda",        status: "unknown" },
    { name: "AgentCore GK_01",       status: "unknown" },
    { name: "AgentCore DEF_L",       status: "unknown" },
    { name: "AgentCore DEF_R",       status: "unknown" },
    { name: "AgentCore MID_01",      status: "unknown" },
    { name: "AgentCore STR_01",      status: "unknown" },
    { name: "DynamoDB",              status: "unknown" },
    { name: "S3 Event Log",          status: "unknown" },
  ])
  const [animFrame, setAnimFrame] = useState(0)
  const [activeMatches, setActiveMatches] = useState<unknown[]>([])

  // Ping backend health
  useEffect(() => {
    async function checkHealth() {
      if (!API_URL) return
      const start = Date.now()
      try {
        const res = await fetch(`${API_URL}health`)
        const latencyMs = Date.now() - start
        const ok = res.ok
        setServices((prev) =>
          prev.map((s) =>
            s.name === "FastAPI Lambda"
              ? { ...s, status: ok ? "healthy" : "degraded", latencyMs }
              : s
          )
        )
        if (ok) {
          setServices((prev) =>
            prev.map((s) =>
              s.name === "API Gateway"
                ? { ...s, status: "healthy", latencyMs }
                : s
            )
          )
        }
      } catch {
        setServices((prev) =>
          prev.map((s) =>
            ["API Gateway", "FastAPI Lambda"].includes(s.name)
              ? { ...s, status: "degraded" }
              : s
          )
        )
      }
    }

    async function fetchActiveMatches() {
      if (!API_URL) return
      try {
        const res = await fetch(`${API_URL}match/list`)
        if (res.ok) {
          const data = await res.json()
          setActiveMatches(data.active_matches ?? [])
        }
      } catch {
        // Non-critical
      }
    }

    checkHealth()
    fetchActiveMatches()
    const interval = setInterval(() => {
      checkHealth()
      fetchActiveMatches()
    }, 10000)

    return () => clearInterval(interval)
  }, [])

  // Animate data flow dots
  useEffect(() => {
    const interval = setInterval(() => setAnimFrame((f) => f + 1), 800)
    return () => clearInterval(interval)
  }, [])

  const statusColor: Record<ServiceStatus["status"], string> = {
    healthy:  "#00FF87",
    degraded: "#FF3D57",
    unknown:  "#6B7FA3",
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      {/* Architecture SVG */}
      <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#F0F4FF] mb-4 uppercase tracking-wider">
          System Architecture
        </h2>
        <div className="overflow-x-auto">
          <svg viewBox="0 0 820 300" className="w-full" style={{ minHeight: "240px" }}>
            {/* Edges */}
            {ARCH_EDGES.map(([from, to]) => {
              const [x1, y1] = getNodeCenter(from)
              const [x2, y2] = getNodeCenter(to)
              return (
                <line
                  key={`${from}-${to}`}
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="rgba(0,212,255,0.2)"
                  strokeWidth="1"
                  strokeDasharray="4 3"
                />
              )
            })}

            {/* Animated flow dots */}
            {ARCH_EDGES.map(([from, to], i) => {
              const [x1, y1] = getNodeCenter(from)
              const [x2, y2] = getNodeCenter(to)
              const t = ((animFrame + i * 3) % 10) / 10
              const cx = x1 + (x2 - x1) * t
              const cy = y1 + (y2 - y1) * t
              return (
                <circle key={`dot-${from}-${to}`} cx={cx} cy={cy} r="2.5"
                  fill="#00D4FF" opacity="0.7" />
              )
            })}

            {/* Nodes */}
            {ARCH_NODES.map((node) => (
              <g key={node.id} transform={`translate(${node.x},${node.y})`}>
                <rect
                  x="0" y="0" width="120" height="36" rx="6"
                  fill="#0F2035"
                  stroke={node.color}
                  strokeWidth="1"
                  strokeOpacity="0.5"
                />
                <text x="10" y="15" fontSize="10" fill={node.color} fontWeight="bold">
                  {node.icon} {node.label}
                </text>
                <text x="10" y="28" fontSize="8" fill="#6B7FA3">
                  {node.id === "nova" ? "us-east-1" :
                   node.id === "agentcore" ? "ARM64 Graviton" :
                   node.id === "backend" ? "ARM64 · 1024MB" :
                   node.id === "mcp" ? "ARM64 · 256MB" : ""}
                </text>
              </g>
            ))}
          </svg>
        </div>
      </div>

      {/* Service health table */}
      <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-[#F0F4FF] uppercase tracking-wider">
            Service Health
          </h2>
          <span className="text-[10px] text-[#6B7FA3] font-mono">
            Polls every 10s
          </span>
        </div>
        <div className="space-y-2">
          {services.map((svc) => (
            <div
              key={svc.name}
              className="flex items-center justify-between px-3 py-2 bg-[#070F1A]
                         rounded border border-[rgba(0,212,255,0.08)]"
            >
              <div className="flex items-center gap-2.5">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: statusColor[svc.status] }}
                />
                <span className="text-sm text-[#C0CFDF]">{svc.name}</span>
              </div>
              <div className="flex items-center gap-4">
                {svc.latencyMs !== undefined && (
                  <span className="text-[10px] font-mono text-[#6B7FA3]">
                    {svc.latencyMs}ms
                  </span>
                )}
                <span
                  className="text-[10px] font-mono uppercase"
                  style={{ color: statusColor[svc.status] }}
                >
                  {svc.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Active matches */}
      <div className="bg-[#0D1B2A] border border-[rgba(0,212,255,0.15)] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#F0F4FF] mb-3 uppercase tracking-wider">
          Active Matches ({activeMatches.length})
        </h2>
        {activeMatches.length === 0 ? (
          <p className="text-[#3D4F6B] text-sm">No active matches on this Lambda instance.</p>
        ) : (
          <div className="space-y-2">
            {(activeMatches as { match_id: string; phase: string; tick: number; scores: { team: string; goals: number }[] }[]).map((m) => (
              <div
                key={m.match_id}
                className="flex items-center justify-between px-3 py-2 bg-[#070F1A]
                           rounded border border-[rgba(0,212,255,0.08)]"
              >
                <span className="text-xs font-mono text-[#00D4FF]">{m.match_id}</span>
                <span className="text-xs text-[#6B7FA3]">{m.phase} · tick {m.tick}</span>
                <span className="text-xs text-[#F0F4FF]">
                  {m.scores.map((s) => `${s.team} ${s.goals}`).join(" — ")}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
