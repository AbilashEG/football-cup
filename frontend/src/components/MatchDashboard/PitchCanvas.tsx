"use client"

import { useRef, useEffect, useMemo } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { Line, Text } from "@react-three/drei"
import * as THREE from "three"
import { GameState, PlayerState, ROLE_COLORS } from "@/types/agent.types"

// ── Constants matching backend physics.py ────────────────────────────────────
const PITCH_W = 60   // x: -30 to 30
const PITCH_H = 40   // y: -20 to 20
const GOAL_HALF = 4
const LERP_FACTOR = 0.08
const DECISION_FLASH_DURATION = 300 // ms

interface PitchCanvasProps {
  gameState: GameState | null
  teamAId?: string
}

// ── Player orb ───────────────────────────────────────────────────────────────
function PlayerOrb({
  player,
  isTeamA,
  flashKey,
}: {
  player: PlayerState
  isTeamA: boolean
  flashKey: number
}) {
  const meshRef = useRef<THREE.Mesh>(null!)
  const lightRef = useRef<THREE.PointLight>(null!)
  const targetPos = useRef(new THREE.Vector3(player.position.x, 0.3, player.position.y))
  const flashRef = useRef(0)

  const color = isTeamA
    ? ROLE_COLORS[player.role]
    : "#FF9900"

  useEffect(() => {
    targetPos.current.set(player.position.x, 0.3, player.position.y)
    flashRef.current = Date.now()
  }, [player.position.x, player.position.y, flashKey])

  useFrame(() => {
    if (!meshRef.current || !lightRef.current) return

    // Lerp position toward target
    meshRef.current.position.lerp(targetPos.current, LERP_FACTOR)

    // Decision flash: emissiveIntensity 8 → 1 over DECISION_FLASH_DURATION ms
    const elapsed = Date.now() - flashRef.current
    const t = Math.min(elapsed / DECISION_FLASH_DURATION, 1)
    const intensity = 8 - t * 7  // 8 → 1
    ;(meshRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = intensity
    lightRef.current.intensity = intensity * 0.4
  })

  return (
    <group>
      <mesh ref={meshRef} position={[player.position.x, 0.3, player.position.y]}>
        <sphereGeometry args={[0.7, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={1}
          roughness={0.3}
          metalness={0.6}
        />
      </mesh>
      <pointLight
        ref={lightRef}
        position={[player.position.x, 1.5, player.position.y]}
        color={color}
        intensity={0.4}
        distance={6}
      />
      {/* Has ball indicator */}
      {player.has_ball && (
        <mesh position={[player.position.x, 1.2, player.position.y]}>
          <sphereGeometry args={[0.18, 8, 8]} />
          <meshStandardMaterial color="#FFFFFF" emissive="#FFFFFF" emissiveIntensity={3} />
        </mesh>
      )}
    </group>
  )
}

// ── Ball ──────────────────────────────────────────────────────────────────────
function Ball({ gameState }: { gameState: GameState | null }) {
  const meshRef = useRef<THREE.Mesh>(null!)
  const targetPos = useRef(new THREE.Vector3(0, 0.25, 0))
  const pulseRef = useRef(0)

  useEffect(() => {
    if (gameState?.ball) {
      targetPos.current.set(
        gameState.ball.position.x,
        0.25,
        gameState.ball.position.y
      )
    }
  }, [gameState?.ball?.position.x, gameState?.ball?.position.y])

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    meshRef.current.position.lerp(targetPos.current, LERP_FACTOR * 1.5)
    // Pulse
    const pulse = Math.sin(clock.elapsedTime * 4) * 0.05 + 1
    meshRef.current.scale.setScalar(pulse)
  })

  return (
    <mesh ref={meshRef} position={[0, 0.25, 0]}>
      <sphereGeometry args={[0.4, 16, 16]} />
      <meshStandardMaterial
        color="#FFFFFF"
        emissive="#FFFFFF"
        emissiveIntensity={2}
        roughness={0.1}
      />
    </mesh>
  )
}

// ── Pitch surface + lines ─────────────────────────────────────────────────────
function PitchGeometry() {
  const lineColor = "rgba(255,255,255,0.4)"

  // Goal objects
  const goalLeft = [
    [-30, 0, -GOAL_HALF], [-30, 2, -GOAL_HALF],
    [-30, 2, GOAL_HALF],  [-30, 0, GOAL_HALF],
  ] as [number, number, number][]

  const goalRight = [
    [30, 0, -GOAL_HALF], [30, 2, -GOAL_HALF],
    [30, 2, GOAL_HALF],  [30, 0, GOAL_HALF],
  ] as [number, number, number][]

  return (
    <group>
      {/* Pitch surface */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <planeGeometry args={[PITCH_W, PITCH_H]} />
        <meshStandardMaterial color="#0A2E0A" roughness={0.9} />
      </mesh>

      {/* Pitch stripe pattern */}
      {Array.from({ length: 6 }, (_, i) => (
        <mesh
          key={i}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[-25 + i * 10, 0.01, 0]}
        >
          <planeGeometry args={[5, PITCH_H]} />
          <meshStandardMaterial color="#0C3510" transparent opacity={0.5} />
        </mesh>
      ))}

      {/* Boundary */}
      <Line points={[[-30,-0.05,-20],[ 30,-0.05,-20],[ 30,-0.05, 20],[-30,-0.05, 20],[-30,-0.05,-20]]}
        color={lineColor} lineWidth={1.5} />

      {/* Centre line */}
      <Line points={[[0,-0.05,-20],[0,-0.05,20]]} color={lineColor} lineWidth={1.2} />

      {/* Centre circle */}
      <Line
        points={Array.from({ length: 65 }, (_, i) => {
          const a = (i / 64) * Math.PI * 2
          return [Math.cos(a) * 6, -0.05, Math.sin(a) * 6] as [number,number,number]
        })}
        color={lineColor} lineWidth={1.2}
      />

      {/* Left penalty box */}
      <Line points={[[-30,-0.05,-10],[-20,-0.05,-10],[-20,-0.05,10],[-30,-0.05,10]]}
        color={lineColor} lineWidth={1.2} />

      {/* Right penalty box */}
      <Line points={[[30,-0.05,-10],[20,-0.05,-10],[20,-0.05,10],[30,-0.05,10]]}
        color={lineColor} lineWidth={1.2} />

      {/* Left goal */}
      <Line points={goalLeft} color="#FF9900" lineWidth={2} />
      <Line points={goalRight} color="#FF9900" lineWidth={2} />

      {/* Goal lines */}
      <Line points={[[-30,-0.05,-GOAL_HALF],[-30,-0.05,GOAL_HALF]]} color="#FF3D57" lineWidth={2.5} />
      <Line points={[[30,-0.05,-GOAL_HALF],[30,-0.05,GOAL_HALF]]} color="#FF3D57" lineWidth={2.5} />

      {/* Centre spot */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <circleGeometry args={[0.3, 12]} />
        <meshStandardMaterial color={lineColor as string} />
      </mesh>
    </group>
  )
}

// ── Scene ─────────────────────────────────────────────────────────────────────
function Scene({ gameState, teamAId }: PitchCanvasProps) {
  const { scene } = useThree()
  const goalFlashRef = useRef(0)
  const prevGoalsRef = useRef(0)

  useEffect(() => {
    scene.fog = new THREE.Fog(0x050A0F, 35, 75)
  }, [scene])

  // Goal flash: ambient light spike
  const totalGoals = (gameState?.scores ?? []).reduce((s, t) => s + t.goals, 0)
  useEffect(() => {
    if (totalGoals > prevGoalsRef.current) {
      goalFlashRef.current = Date.now()
    }
    prevGoalsRef.current = totalGoals
  }, [totalGoals])

  const ambientRef = useRef<THREE.AmbientLight>(null!)
  useFrame(() => {
    if (!ambientRef.current) return
    const elapsed = Date.now() - goalFlashRef.current
    const t = Math.min(elapsed / 600, 1)
    ambientRef.current.intensity = t < 0.3 ? 3 - t * 6 : 0.3
  })

  const players = gameState?.players ?? []

  return (
    <>
      <ambientLight ref={ambientRef} intensity={0.3} />
      {/* Corner point lights — AWS Orange */}
      <pointLight position={[-28, 8, -18]} color="#FF9900" intensity={1.2} distance={40} />
      <pointLight position={[ 28, 8, -18]} color="#FF9900" intensity={1.2} distance={40} />
      <pointLight position={[-28, 8,  18]} color="#FF9900" intensity={1.2} distance={40} />
      <pointLight position={[ 28, 8,  18]} color="#FF9900" intensity={1.2} distance={40} />

      <PitchGeometry />
      <Ball gameState={gameState} />

      {players.map((p) => (
        <PlayerOrb
          key={p.player_id}
          player={p}
          isTeamA={p.team_id === teamAId}
          flashKey={gameState?.tick ?? 0}
        />
      ))}
    </>
  )
}

// ── Public component ──────────────────────────────────────────────────────────
export default function PitchCanvas({ gameState, teamAId }: PitchCanvasProps) {
  return (
    <div style={{ height: "520px", width: "100%" }}>
      <Canvas
        style={{ height: "100%", width: "100%" }}
        camera={{
          position: [0, 28, 6],
          fov: 55,
          near: 0.1,
          far: 200,
        }}
        onCreated={({ camera }) => {
          camera.lookAt(0, 0, 0)
        }}
      >
        <Scene gameState={gameState} teamAId={teamAId} />
      </Canvas>
    </div>
  )
}
