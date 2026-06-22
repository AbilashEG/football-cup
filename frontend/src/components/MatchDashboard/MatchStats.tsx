"use client"

import { GameState, MatchStats as MatchStatsType } from "@/types/agent.types"

interface MatchStatsProps {
  gameState: GameState | null
  stats: MatchStatsType | null
}

function StatBar({
  label,
  valueA,
  valueB,
  unit = "",
  colorA = "#00D4FF",
  colorB = "#FF9900",
}: {
  label: string
  valueA: number
  valueB: number
  unit?: string
  colorA?: string
  colorB?: string
}) {
  const total = valueA + valueB || 1
  const pctA = (valueA / total) * 100
  const pctB = (valueB / total) * 100

  return (
    <div className="mb-3">
      <div className="flex justify-between text-[11px] text-[#6B7FA3] mb-1">
        <span style={{ color: colorA }} className="font-mono font-bold">
          {valueA.toFixed(0)}{unit}
        </span>
        <span className="text-[#8090A8]">{label}</span>
        <span style={{ color: colorB }} className="font-mono font-bold">
          {valueB.toFixed(0)}{unit}
        </span>
      </div>
      <div className="flex h-1.5 rounded-full overflow-hidden bg-[#0A1628]">
        <div
          className="transition-all duration-500"
          style={{ width: `${pctA}%`, backgroundColor: colorA }}
        />
        <div
          className="transition-all duration-500"
          style={{ width: `${pctB}%`, backgroundColor: colorB }}
        />
      </div>
    </div>
  )
}

function ScoreBoard({ gameState }: { gameState: GameState }) {
  const [a, b] = gameState.scores
  const phaseLabel: Record<string, string> = {
    PRE_MATCH:   "PRE-MATCH",
    FIRST_HALF:  "1ST HALF",
    HALF_TIME:   "HALF TIME",
    SECOND_HALF: "2ND HALF",
    FULL_TIME:   "FULL TIME",
  }

  const mins = Math.floor(gameState.clock_seconds / 60)
  const secs = gameState.clock_seconds % 60
  const clockStr = `${mins}:${String(secs).padStart(2, "0")}`

  return (
    <div className="flex items-center justify-between mb-4 bg-[#0A1628] rounded-lg px-4 py-3">
      {/* Team A */}
      <div className="text-center">
        <div className="text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
          {a?.team_name ?? "Team A"}
        </div>
        <div className="text-3xl font-black text-[#00D4FF] font-mono">
          {a?.goals ?? 0}
        </div>
      </div>

      {/* Clock + phase */}
      <div className="text-center">
        <div className="text-xs text-[#FF9900] font-bold tracking-widest mb-0.5">
          {phaseLabel[gameState.phase] ?? gameState.phase}
        </div>
        <div className="text-xl font-mono text-[#F0F4FF] font-bold">{clockStr}</div>
        <div className="text-[10px] text-[#3D4F6B] font-mono mt-0.5">
          tick {gameState.tick}
        </div>
      </div>

      {/* Team B */}
      <div className="text-center">
        <div className="text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-1">
          {b?.team_name ?? "Team B"}
        </div>
        <div className="text-3xl font-black text-[#FF9900] font-mono">
          {b?.goals ?? 0}
        </div>
      </div>
    </div>
  )
}

function PlayerStaminaRow({ player }: { player: GameState["players"][number] }) {
  const staminaColor =
    player.stamina > 60 ? "#00FF87" :
    player.stamina > 30 ? "#FF9900" : "#FF3D57"

  return (
    <div className="flex items-center gap-2 mb-1.5">
      <span className="text-[10px] font-mono text-[#6B7FA3] w-14 shrink-0">
        {player.player_id}
      </span>
      <div className="flex-1 h-1 bg-[#0A1628] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${player.stamina}%`,
            backgroundColor: staminaColor,
          }}
        />
      </div>
      <span
        className="text-[10px] font-mono w-8 text-right"
        style={{ color: staminaColor }}
      >
        {player.stamina.toFixed(0)}
      </span>
      {player.has_ball && (
        <span className="text-[9px] text-[#FFFFFF] bg-[#1A3040] px-1 rounded">
          ●
        </span>
      )}
    </div>
  )
}

export default function MatchStats({ gameState, stats }: MatchStatsProps) {
  if (!gameState) {
    return (
      <div className="bg-[#0D1B2A] rounded-lg border border-[rgba(0,212,255,0.15)] p-4 h-full flex items-center justify-center">
        <span className="text-[#3D4F6B] text-sm">No match active</span>
      </div>
    )
  }

  const [a, b] = gameState.scores
  const teamAId = a?.team_id
  const teamBId = b?.team_id

  // Aggregate stats by team from stats object
  const teamAShotsTotal = Object.entries(stats?.shots ?? {})
    .filter(([pid]) => gameState.players.find(p => p.player_id === pid)?.team_id === teamAId)
    .reduce((s, [, v]) => s + v, 0)
  const teamBShotsTotal = Object.entries(stats?.shots ?? {})
    .filter(([pid]) => gameState.players.find(p => p.player_id === pid)?.team_id === teamBId)
    .reduce((s, [, v]) => s + v, 0)

  const teamAPassTotal = Object.entries(stats?.passes ?? {})
    .filter(([pid]) => gameState.players.find(p => p.player_id === pid)?.team_id === teamAId)
    .reduce((s, [, v]) => s + v, 0)
  const teamBPassTotal = Object.entries(stats?.passes ?? {})
    .filter(([pid]) => gameState.players.find(p => p.player_id === pid)?.team_id === teamBId)
    .reduce((s, [, v]) => s + v, 0)

  // Possession from stats
  const posA = Object.entries(stats?.possession_pct ?? {})
    .filter(([pid]) => gameState.players.find(p => p.player_id === pid)?.team_id === teamAId)
    .reduce((s, [, v]) => s + v, 0)
  const posB = 100 - posA

  const teamAPlayers = gameState.players.filter(p => p.team_id === teamAId)
  const teamBPlayers = gameState.players.filter(p => p.team_id === teamBId)

  return (
    <div className="bg-[#0D1B2A] rounded-lg border border-[rgba(0,212,255,0.15)] p-4 h-full overflow-y-auto">
      <ScoreBoard gameState={gameState} />

      {/* Match stats bars */}
      <div className="mb-4">
        <div className="text-[10px] text-[#6B7FA3] uppercase tracking-wider mb-2">Match Stats</div>
        <StatBar label="Possession %" valueA={posA} valueB={posB} unit="%" />
        <StatBar label="Shots" valueA={teamAShotsTotal} valueB={teamBShotsTotal} />
        <StatBar label="Passes" valueA={teamAPassTotal} valueB={teamBPassTotal} />
      </div>

      {/* Stamina — Team A */}
      <div className="mb-3">
        <div className="text-[10px] text-[#00D4FF] uppercase tracking-wider mb-2">
          {a?.team_name ?? "Team A"} — Stamina
        </div>
        {teamAPlayers.map(p => <PlayerStaminaRow key={p.player_id} player={p} />)}
      </div>

      {/* Stamina — Team B */}
      <div>
        <div className="text-[10px] text-[#FF9900] uppercase tracking-wider mb-2">
          {b?.team_name ?? "Team B"} — Stamina
        </div>
        {teamBPlayers.map(p => <PlayerStaminaRow key={p.player_id} player={p} />)}
      </div>
    </div>
  )
}
