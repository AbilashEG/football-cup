"use client"

import { useState } from "react"
import NavBar from "@/components/NavBar"
import MatchDashboard from "@/components/MatchDashboard/MatchDashboard"
import SquadBuilder from "@/components/SquadBuilder/SquadBuilder"
import StrategyTuner from "@/components/StrategyTuner/StrategyTuner"
import StackMonitor from "@/components/StackMonitor/StackMonitor"
import { ViewMode } from "@/types/agent.types"

// Mock data used when no live match is running
import { mockGameState } from "@/lib/mockData"

export default function Page() {
  const [view, setView] = useState<ViewMode>("match")

  // In a real session the matchPhase would come from the WebSocket;
  // the NavBar receives it via MatchDashboard → lifted state.
  // For simplicity, we use a shared state atom here.
  const [matchPhase, setMatchPhase] = useState<string | undefined>(undefined)

  return (
    <div className="flex flex-col h-full min-h-screen">
      <NavBar
        view={view}
        onViewChange={setView}
        matchPhase={matchPhase}
      />

      <main className="flex-1 overflow-y-auto p-4 lg:p-6">
        {view === "match" && (
          <MatchDashboard />
        )}
        {view === "squad" && (
          <SquadBuilder />
        )}
        {view === "strategy" && (
          <StrategyTuner />
        )}
        {view === "stack" && (
          <StackMonitor />
        )}
      </main>

      {/* Footer */}
      <footer className="shrink-0 border-t border-[rgba(0,212,255,0.1)] px-6 py-2
                         flex items-center justify-between">
        <span className="text-[10px] text-[#3D4F6B] font-mono">
          AWS Agentic Football Cup · Strands Agents SDK · amazon.nova-micro-v1:0
        </span>
        <span className="text-[10px] text-[#3D4F6B] font-mono">
          AgentCore Runtime · ARM64 Graviton · us-east-1
        </span>
      </footer>
    </div>
  )
}
