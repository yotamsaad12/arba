import { Edges } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef, type ReactNode } from "react";
import * as THREE from "three";
import { INK, toon } from "./materials";

type Vec3 = [number, number, number];

/**
 * Eases its children's scale toward `to` (0..1) along the given axes. Starts from 0, so every
 * part builds itself up when the scene first appears. `delay` staggers neighbouring parts.
 */
export function Grow({
  to,
  axes = "y",
  position,
  rotation,
  delay = 0,
  speed = 3.2,
  children,
}: {
  to: number;
  axes?: "y" | "xz" | "xyz" | "x";
  position?: Vec3;
  rotation?: Vec3;
  delay?: number;
  speed?: number;
  children: ReactNode;
}) {
  const ref = useRef<THREE.Group>(null);
  const state = useRef({ value: 0, waited: 0 });

  useFrame((_, dt) => {
    const group = ref.current;
    if (!group) return;
    const s = state.current;
    s.waited += dt;
    if (s.waited < delay) return;
    s.value = THREE.MathUtils.damp(s.value, to, speed, Math.min(dt, 0.1));
    const v = Math.max(s.value, 0.0001);
    group.scale.set(axes.includes("x") ? v : 1, axes.includes("y") ? v : 1, axes.includes("z") ? v : 1);
    group.visible = s.value > 0.003;
  });

  return (
    <group ref={ref} position={position} rotation={rotation} visible={false}>
      {children}
    </group>
  );
}

/** A box with its base at y=0 (so it grows upward), cel-shaded with ink outlines. */
export function Block({
  size,
  position = [0, 0, 0],
  color,
  material,
  edges = true,
  rotation,
}: {
  size: Vec3;
  position?: Vec3;
  color?: string;
  material?: THREE.Material;
  edges?: boolean;
  rotation?: Vec3;
}) {
  const [w, h, d] = size;
  return (
    <mesh
      position={[position[0], position[1] + h / 2, position[2]]}
      rotation={rotation}
      material={material ?? toon(color ?? "#ffffff")}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[w, h, d]} />
      {edges && <Edges color={INK} threshold={20} />}
    </mesh>
  );
}

/** Triangular gable roof along the x axis, base at y=0. */
export function GableRoof({
  width,
  depth,
  height,
  position = [0, 0, 0],
  color,
}: {
  width: number;
  depth: number;
  height: number;
  position?: Vec3;
  color: string;
}) {
  const shape = new THREE.Shape();
  shape.moveTo(-depth / 2, 0);
  shape.lineTo(depth / 2, 0);
  shape.lineTo(0, height);
  shape.closePath();
  return (
    <mesh
      position={[position[0] - width / 2, position[1], position[2]]}
      rotation={[0, Math.PI / 2, 0]}
      material={toon(color)}
      castShadow
    >
      <extrudeGeometry args={[shape, { depth: width, bevelEnabled: false }]} />
      <Edges color={INK} threshold={20} />
    </mesh>
  );
}
