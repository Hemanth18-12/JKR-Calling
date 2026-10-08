"use client";

import { Float, Html } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import * as React from "react";
import * as THREE from "three";

interface VoiceOrbProps {
  isTyping?: boolean;
}

function WaveformParticleRing({ isTyping }: { isTyping: boolean }) {
  const pointsRef = React.useRef<THREE.Points>(null);
  const count = 96;

  const [positions] = React.useState(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const radius = 2.4;
      pos[i * 3] = Math.cos(angle) * radius;
      pos[i * 3 + 1] = 0;
      pos[i * 3 + 2] = Math.sin(angle) * radius;
    }
    return pos;
  });

  useFrame(({ clock }) => {
    if (!pointsRef.current) return;
    const time = clock.getElapsedTime();
    const positionAttr = pointsRef.current.geometry.attributes.position as THREE.BufferAttribute;
    const array = positionAttr.array as Float32Array;

    const intensity = isTyping ? 0.35 : 0.12;
    const speed = isTyping ? 3.5 : 1.8;

    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const baseRadius = 2.4;
      const wave = Math.sin(angle * 6 + time * speed) * intensity;
      const r = baseRadius + wave;
      array[i * 3] = Math.cos(angle) * r;
      array[i * 3 + 1] = Math.cos(angle * 4 + time * 2) * (intensity * 0.8);
      array[i * 3 + 2] = Math.sin(angle) * r;
    }
    positionAttr.needsUpdate = true;
    pointsRef.current.rotation.y = time * 0.15;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.06}
        color="#FFD400"
        transparent
        opacity={0.85}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function CentralVoiceNucleus({ isTyping }: { isTyping: boolean }) {
  const coreRef = React.useRef<THREE.Mesh>(null);
  const outerGlassRef = React.useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (coreRef.current) {
      const baseScale = isTyping ? 1.15 : 1.0;
      const pulse = Math.sin(t * (isTyping ? 4 : 2)) * 0.06;
      coreRef.current.scale.setScalar(baseScale + pulse);
    }
    if (outerGlassRef.current) {
      outerGlassRef.current.rotation.y = t * 0.2;
      outerGlassRef.current.rotation.x = Math.sin(t * 0.1) * 0.1;
    }
  });

  return (
    <group>
      {/* Internal Glowing Gold Core */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[1.1, 32, 32]} />
        <meshStandardMaterial
          color="#FFD400"
          emissive="#FFA000"
          emissiveIntensity={isTyping ? 0.9 : 0.55}
          roughness={0.15}
          metalness={0.85}
        />
      </mesh>

      {/* Outer Translucent Glass Envelope */}
      <mesh ref={outerGlassRef}>
        <sphereGeometry args={[1.5, 32, 32]} />
        <meshStandardMaterial
          color="#FFE57F"
          roughness={0.08}
          metalness={0.1}
          transparent
          opacity={0.32}
        />
      </mesh>
    </group>
  );
}

function MultilingualGlyphs() {
  return (
    <group>
      {/* Telugu */}
      <Float speed={2} rotationIntensity={0.2} floatIntensity={0.6}>
        <Html position={[0, 2.3, 0]} center distanceFactor={10}>
          <div className="select-none rounded-full border border-primary/40 bg-surface/85 px-3 py-1 text-xs font-bold text-primary backdrop-blur-md shadow-md shadow-primary/20 pointer-events-none whitespace-nowrap">
            నమస్తే (Telugu)
          </div>
        </Html>
      </Float>

      {/* Hindi */}
      <Float speed={2.4} rotationIntensity={0.2} floatIntensity={0.5}>
        <Html position={[2.4, -0.6, 0.8]} center distanceFactor={10}>
          <div className="select-none rounded-full border border-secondary/40 bg-surface/85 px-3 py-1 text-xs font-bold text-amber-400 backdrop-blur-md shadow-md shadow-secondary/20 pointer-events-none whitespace-nowrap">
            नमस्ते (Hindi)
          </div>
        </Html>
      </Float>

      {/* English */}
      <Float speed={1.8} rotationIntensity={0.2} floatIntensity={0.5}>
        <Html position={[-2.4, -0.4, 0.4]} center distanceFactor={10}>
          <div className="select-none rounded-full border border-border bg-surface/85 px-3 py-1 text-xs font-bold text-foreground backdrop-blur-md shadow-md pointer-events-none whitespace-nowrap">
            Hello (English)
          </div>
        </Html>
      </Float>
    </group>
  );
}

function SceneGroup({ isTyping }: { isTyping: boolean }) {
  const groupRef = React.useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current) return;
    // Smooth lerp tilt following mouse cursor
    const targetX = state.pointer.y * 0.25;
    const targetY = state.pointer.x * 0.35;
    groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, targetX, 0.05);
    groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, targetY, 0.05);
  });

  return (
    <group ref={groupRef}>
      <ambientLight intensity={0.6} />
      <pointLight position={[4, 5, 4]} color="#FFD400" intensity={1.8} />
      <pointLight position={[-4, -3, -4]} color="#FF9F1C" intensity={0.9} />
      <CentralVoiceNucleus isTyping={isTyping} />
      <WaveformParticleRing isTyping={isTyping} />
      <MultilingualGlyphs />
    </group>
  );
}

export default function VoiceOrbScene({ isTyping = false }: VoiceOrbProps) {
  const [active, setActive] = React.useState(true);

  // Pause rendering when tab is hidden or blur
  React.useEffect(() => {
    const handleVisibility = () => {
      setActive(!document.hidden);
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  return (
    <div className="relative h-full w-full">
      <Canvas
        camera={{ position: [0, 0, 6], fov: 45 }}
        dpr={[1, 1.5]}
        frameloop={active ? "always" : "never"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <SceneGroup isTyping={isTyping} />
      </Canvas>
    </div>
  );
}
