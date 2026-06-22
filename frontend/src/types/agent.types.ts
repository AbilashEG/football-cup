// Shared TypeScript types — mirrors Python Pydantic models exactly

export type CommandType =
  | "MOVE_TO"
  | "PASS"
  | "SHOOT"
  | "DRIBBLE"
  | "PRESS_BALL"
  | "MARK"
  | "INTERCEPT"
  | "TACKLE"
  | "CLEAR"
  | "IDLE"
  | "GOALKEEPER_DIVE"

export type PlayerRole = "GOALKEEPER" | "DEFENDER" | "MIDFIELDER" | "STRIKER"

export type GamePhase =
  | "PRE_MATCH"
  | "FIRST_HALF"
  | "HALF_TIME"
  | "SECOND_HALF"
  | "FULL_TIME"

export interface Position {
  x: number
  y: number
}

export interface Velocity {
  vx: number
  vy: number
}

export interface AgentCommand {
  type: CommandType
  target_player_id?: string | null
  target_position?: Position | null
  rationale: string
}

export interface PlayerState {
  player_id: string
  team_id: string
  role: PlayerRole
  position: Position
  velocity: Velocity
  stamina: number
  has_ball: boolean
  is_active: boolean
}

export interface BallState {
  position: Position
  velocity: Velocity
  last_touched_by?: string | null
}

export interface TeamScore {
  team_id: string
  team_name: string
  goals: number
}

export interface GameState {
  match_id: string
  tick: number
  clock_seconds: number
  phase: GamePhase
  players: PlayerState[]
  ball: BallState
  scores: TeamScore[]
  human_hint?: string | null
}

export interface TickEvent {
  tick: number
  match_id: string
  timestamp: string
  player_id: string
  command: AgentCommand
  latency_ms: number
  game_state_snapshot: GameState
}

// Frontend-only types

export type ViewMode = "squad" | "match" | "strategy" | "stack"

export type ConnectionStatus = "connecting" | "connected" | "disconnected"

export interface AgentConfig {
  player_id: string
  role: PlayerRole
  system_prompt: string
  agentcore_endpoint?: string
}

export interface SquadConfig {
  squad_id?: string
  squad_name: string
  team_color: string
  formation: "4-1" | "3-2" | "2-2-1" | "2-3"
  agents: AgentConfig[]
  owner_id?: string
}

export interface MatchStats {
  match_id: string
  total_ticks: number
  possession_pct: Record<string, number>
  shots: Record<string, number>
  passes: Record<string, number>
  tackles: Record<string, number>
  avg_latency_ms: Record<string, number>
  timeouts: Record<string, number>
  command_counts: Record<string, Record<CommandType, number>>
}

export const ROLE_COLORS: Record<PlayerRole, string> = {
  GOALKEEPER: "#FF9900",
  DEFENDER:   "#00D4FF",
  MIDFIELDER: "#00FF87",
  STRIKER:    "#FF3D57",
}

export const ROLE_LABELS: Record<PlayerRole, string> = {
  GOALKEEPER: "GK",
  DEFENDER:   "DEF",
  MIDFIELDER: "MID",
  STRIKER:    "STR",
}

export const COMMAND_COLORS: Record<CommandType, string> = {
  MOVE_TO:         "#6B7FA3",
  PASS:            "#00D4FF",
  SHOOT:           "#FF3D57",
  DRIBBLE:         "#FF9900",
  PRESS_BALL:      "#FF6B35",
  MARK:            "#9B59B6",
  INTERCEPT:       "#00FF87",
  TACKLE:          "#E74C3C",
  CLEAR:           "#F39C12",
  IDLE:            "#3D4F6B",
  GOALKEEPER_DIVE: "#FF9900",
}
