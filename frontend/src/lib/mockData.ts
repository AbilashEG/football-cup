import { GameState } from "@/types/agent.types"

export const mockGameState: GameState = {
  match_id: "DEMO",
  tick: 0,
  clock_seconds: 0,
  phase: "PRE_MATCH",
  players: [
    { player_id: "GK_01",  team_id: "team_a", role: "GOALKEEPER",  position: { x: -28, y: 0  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "DEF_L",  team_id: "team_a", role: "DEFENDER",    position: { x: -15, y: -7 }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "DEF_R",  team_id: "team_a", role: "DEFENDER",    position: { x: -15, y: 7  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "MID_01", team_id: "team_a", role: "MIDFIELDER",  position: { x: 0,   y: 0  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: true,  is_active: true },
    { player_id: "STR_01", team_id: "team_a", role: "STRIKER",     position: { x: 12,  y: 0  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "B_GK_01",  team_id: "team_b", role: "GOALKEEPER",  position: { x: 28,  y: 0  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "B_DEF_L",  team_id: "team_b", role: "DEFENDER",    position: { x: 15,  y: -7 }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "B_DEF_R",  team_id: "team_b", role: "DEFENDER",    position: { x: 15,  y: 7  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "B_MID_01", team_id: "team_b", role: "MIDFIELDER",  position: { x: 0,   y: 2  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
    { player_id: "B_STR_01", team_id: "team_b", role: "STRIKER",     position: { x: -12, y: 0  }, velocity: { vx: 0, vy: 0 }, stamina: 100, has_ball: false, is_active: true },
  ],
  ball: {
    position: { x: 0, y: 0 },
    velocity: { vx: 0, vy: 0 },
    last_touched_by: "MID_01",
  },
  scores: [
    { team_id: "team_a", team_name: "Crimson Rovers", goals: 0 },
    { team_id: "team_b", team_name: "Azure FC",        goals: 0 },
  ],
  human_hint: null,
}
