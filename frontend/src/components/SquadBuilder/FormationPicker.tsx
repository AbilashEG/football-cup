"use client"

import { SquadConfig } from "@/types/agent.types"

type Formation = SquadConfig["formation"]

const FORMATIONS: { id: Formation; label: string; description: string }[] = [
  { id: "4-1",   label: "4-1",   description: "2 DEF · 1 MID · 1 STR" },
  { id: "3-2",   label: "3-2",   description: "1 GK · 2 DEF · 2 ATT" },
  { id: "2-2-1", label: "2-2-1", description: "2 DEF · 2 MID · 1 STR" },
  { id: "2-3",   label: "2-3",   description: "2 DEF · 3 FWD (high press)" },
]

// Predefined player positions per formation [x, y] — scaled to SVG 200×140 viewBox
// Pitch: x -30→30, y -20→20. Map to SVG: svgX = (x+30)/60*200, svgY = (y+20)/40*140
const FORMATION_POSITIONS: Record<Formation, Record<string, [number, number]>> = {
  "4-1": {
    GK_01:  [6,  70],
    DEF_L:  [50, 40],
    DEF_R:  [50, 100],
    MID_01: [100, 70],
    STR_01: [160, 70],
  },
  "3-2": {
    GK_01:  [6,  70],
    DEF_L:  [55, 35],
    DEF_R:  [55, 105],
    MID_01: [110, 50],
    STR_01: [110, 90],
  },
  "2-2-1": {
    GK_01:  [6,  70],
    DEF_L:  [50, 45],
    DEF_R:  [50, 95],
    MID_01: [100, 45],
    STR_01: [155, 70],
  },
  "2-3": {
    GK_01:  [6,  70],
    DEF_L:  [55, 45],
    DEF_R:  [55, 95],
    MID_01: [115, 70],
    STR_01: [160, 55],
  },
}

const PLAYER_COLORS: Record<string, string> = {
  GK_01:  "#FF9900",
  DEF_L:  "#00D4FF",
  DEF_R:  "#00D4FF",
  MID_01: "#00FF87",
  STR_01: "#FF3D57",
}

interface FormationPickerProps {
  formation: Formation
  onChange: (f: Formation) => void
  teamColor?: string
}

export default function FormationPicker({
  formation,
  onChange,
  teamColor = "#00D4FF",
}: FormationPickerProps) {
  const positions = FORMATION_POSITIONS[formation]

  return (
    <div className="flex flex-col gap-3">
      {/* Formation selector buttons */}
      <div className="flex gap-2 flex-wrap">
        {FORMATIONS.map((f) => (
          <button
            key={f.id}
            onClick={() => onChange(f.id)}
            className={[
              "flex flex-col items-center px-3 py-2 rounded border text-xs transition-all duration-150",
              formation === f.id
                ? "border-[#00D4FF] bg-[rgba(0,212,255,0.1)] text-[#00D4FF]"
                : "border-[rgba(0,212,255,0.15)] text-[#6B7FA3] hover:border-[rgba(0,212,255,0.3)]",
            ].join(" ")}
          >
            <span className="font-bold text-sm">{f.label}</span>
            <span className="text-[9px] mt-0.5 opacity-70">{f.description}</span>
          </button>
        ))}
      </div>

      {/* SVG pitch preview */}
      <div className="bg-[#070F1A] rounded-lg border border-[rgba(0,212,255,0.1)] overflow-hidden">
        <svg
          viewBox="0 0 200 140"
          className="w-full"
          style={{ height: "160px" }}
        >
          {/* Pitch surface */}
          <rect x="0" y="0" width="200" height="140" fill="#0A2E0A" />

          {/* Pitch stripes */}
          {[0,1,2,3,4,5].map(i => (
            <rect key={i} x={i*33} y="0" width="16" height="140"
              fill="#0C3510" opacity="0.5" />
          ))}

          {/* Boundary */}
          <rect x="4" y="4" width="192" height="132"
            fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />

          {/* Centre line */}
          <line x1="100" y1="4" x2="100" y2="136"
            stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />

          {/* Centre circle */}
          <circle cx="100" cy="70" r="18"
            fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />

          {/* Left penalty box */}
          <rect x="4" y="42" width="33" height="56"
            fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="0.6" />

          {/* Right penalty box */}
          <rect x="163" y="42" width="33" height="56"
            fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="0.6" />

          {/* Goals */}
          <rect x="0" y="57" width="4" height="26" fill="#FF9900" opacity="0.6" />
          <rect x="196" y="57" width="4" height="26" fill="#FF9900" opacity="0.6" />

          {/* Player dots */}
          {Object.entries(positions).map(([pid, [px, py]]) => (
            <g key={pid}>
              <circle
                cx={px} cy={py} r="7"
                fill={PLAYER_COLORS[pid] ?? teamColor}
                opacity="0.85"
              />
              <text
                x={px} y={py + 1}
                textAnchor="middle" dominantBaseline="middle"
                fontSize="5" fontWeight="bold" fill="rgba(0,0,0,0.8)"
              >
                {pid.replace("_", "")}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  )
}
