import { Edges } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { SceneModel } from "../scene/model";
import { COLORS, INK, toon } from "./materials";
import { Block, Grow } from "./primitives";

// House geometry in world units (~1 unit = 1 m).
export const HOUSE = { width: 8, depth: 6, floorH: 3, slab: 0.3, base: 0.4 } as const;
const { width: W, depth: D, floorH: H, slab: SLAB, base: BASE } = HOUSE;

export function floorsShown(model: SceneModel) {
  return Math.min(Math.max(model.floors.length, 1), 4);
}

/** Top of the structure in world units. */
export function houseHeight(model: SceneModel) {
  return BASE + floorsShown(model) * H;
}

export function House({ model }: { model: SceneModel }) {
  const s = model.stage;
  const n = floorsShown(model);
  const floors = model.floors.slice(0, n);
  const total = n * H;
  const builtFloors = floors.filter((f) => f > 0).length;
  const structureUp = floors.every((f) => f >= 1);
  const showScaffold = builtFloors > 0 && s.finish < 0.6;
  const columns = useMemo(
    () =>
      [-W / 2 + 0.3, 0, W / 2 - 0.3].flatMap((x) =>
        [-D / 2 + 0.3, D / 2 - 0.3].map((z) => [x, z] as const),
      ),
    [],
  );

  // Walls go from bare blocks to plaster as finishing starts.
  const wallMaterial = useMemo(() => toon(COLORS.block).clone(), []);
  const plaster = useMemo(() => new THREE.Color(COLORS.plaster), []);
  const block = useMemo(() => new THREE.Color(COLORS.block), []);
  useFrame((_, dt) => {
    wallMaterial.color.lerp(s.finish >= 0.3 ? plaster : block, Math.min(1, dt * 2));
  });

  const windows = useMemo(() => {
    const list: { pos: [number, number, number]; size: [number, number, number]; door?: boolean }[] = [];
    for (let i = 0; i < n; i++) {
      const y = BASE + i * H;
      const front = D / 2 + 0.11;
      if (i === 0) {
        list.push({ pos: [0.2, y, front], size: [1.2, 2.2, 0.12], door: true });
        list.push({ pos: [-2.4, y + 0.9, front], size: [1.8, 1.2, 0.12] });
        list.push({ pos: [2.6, y + 0.9, front], size: [1.8, 1.2, 0.12] });
      } else {
        for (const x of [-2.6, 0, 2.6]) list.push({ pos: [x, y + 0.9, front], size: [1.6, 1.3, 0.12] });
      }
      for (const z of [-1.3, 1.3]) {
        list.push({ pos: [W / 2 + 0.11, y + 0.9, z], size: [0.12, 1.2, 1.5] });
      }
    }
    return list;
  }, [n]);

  return (
    <group>
      {/* Foundations: dug pit with rebar mat, soil heaps, then the poured slab. */}
      <Grow to={s.foundations > 0 && s.foundations < 1 ? 1 : 0} axes="xz" position={[0, 0.01, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} material={toon(COLORS.soil)}>
          <planeGeometry args={[W + 1.6, D + 1.6]} />
        </mesh>
        {s.foundations >= 0.5 &&
          Array.from({ length: 9 }, (_, k) => (
            <Block key={`x${k}`} size={[W + 0.8, 0.06, 0.06]} position={[0, 0.05, -D / 2 + 0.3 + k * 0.67]} color={COLORS.amberDark} edges={false} />
          ))}
      </Grow>
      {[
        [-W / 2 - 2.2, D / 2 - 1],
        [W / 2 + 2, -D / 2 + 0.5],
      ].map(([x, z], k) => (
        <Grow key={k} to={s.foundations > 0 && s.foundations < 1 ? 1 : 0} axes="xyz" position={[x!, 0, z!]} delay={0.2 * k}>
          <mesh material={toon(COLORS.soil)} scale={[1.6, 0.9, 1.3]}>
            <sphereGeometry args={[1, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <Edges color={INK} threshold={25} />
          </mesh>
        </Grow>
      ))}
      <Grow to={s.foundations >= 1 ? 1 : 0} axes="xz">
        <Block size={[W + 0.6, BASE, D + 0.6]} color={COLORS.concrete} />
      </Grow>

      {/* Skeleton: per floor, columns rise, formwork, then the slab is poured. */}
      {floors.map((f, i) => {
        const y = BASE + i * H;
        return (
          <group key={i}>
            {columns.map(([x, z], k) => (
              <Grow key={k} to={Math.min(1, f * 1.6)} position={[x, y, z]} delay={k * 0.05}>
                <Block size={[0.36, H - SLAB, 0.36]} color={COLORS.concrete} />
              </Grow>
            ))}
            {f > 0 &&
              f < 1 &&
              columns.map(([x, z], k) => (
                <Block key={`r${k}`} size={[0.05, 0.9, 0.05]} position={[x, y + H - SLAB, z]} color={COLORS.amberDark} edges={false} />
              ))}
            <Grow to={f >= 0.4 && f < 1 ? 1 : 0} axes="xz" position={[0, y + H - SLAB, 0]}>
              <mesh position={[0, SLAB / 2, 0]}>
                <boxGeometry args={[W + 0.6, SLAB, D + 0.6]} />
                <meshBasicMaterial transparent opacity={0} />
                <Edges color={COLORS.wood} threshold={20} />
              </mesh>
            </Grow>
            <Grow to={f >= 1 ? 1 : 0} axes="xz" position={[0, y + H - SLAB, 0]} speed={2.6}>
              <Block size={[W + 0.6, SLAB, D + 0.6]} color={COLORS.concrete} />
            </Grow>
          </group>
        );
      })}

      {/* Protected room in the back corner of the ground floor. */}
      <Grow to={s.mamad > 0 ? 0.3 + s.mamad * 0.7 : 0} position={[-W / 2 + 1.6, BASE, -D / 2 + 1.5]}>
        <Block size={[2.6, H - SLAB, 2.4]} color={COLORS.concreteDark} />
      </Grow>

      {/* Envelope: walls rise around the frame. */}
      <Grow to={Math.min(1, s.envelope * 1.25)} position={[0, BASE, 0]} speed={2.4}>
        <Block size={[W, total - SLAB, 0.2]} position={[0, 0, D / 2 - 0.1]} material={wallMaterial} />
        <Block size={[W, total - SLAB, 0.2]} position={[0, 0, -D / 2 + 0.1]} material={wallMaterial} />
        <Block size={[0.2, total - SLAB, D - 0.4]} position={[W / 2 - 0.1, 0, 0]} material={wallMaterial} />
        <Block size={[0.2, total - SLAB, D - 0.4]} position={[-W / 2 + 0.1, 0, 0]} material={wallMaterial} />
      </Grow>

      {/* Roof waterproofing and parapet. */}
      <Grow to={s.envelope >= 1 && structureUp ? 1 : 0} axes="xz" position={[0, BASE + total, 0]}>
        <Block size={[W + 0.6, 0.08, D + 0.6]} color="#3f4652" edges={false} />
        <Block size={[W + 0.6, 0.6, 0.15]} position={[0, 0, D / 2 + 0.22]} color={COLORS.plaster} />
        <Block size={[W + 0.6, 0.6, 0.15]} position={[0, 0, -D / 2 - 0.22]} color={COLORS.plaster} />
        <Block size={[0.15, 0.6, D + 0.6]} position={[W / 2 + 0.22, 0, 0]} color={COLORS.plaster} />
        <Block size={[0.15, 0.6, D + 0.6]} position={[-W / 2 - 0.22, 0, 0]} color={COLORS.plaster} />
      </Grow>

      {/* Systems: water riser and conduit on the side wall, gone once plastered over. */}
      <Grow to={s.systems > 0 && s.finish < 0.6 ? 1 : 0} position={[W / 2 + 0.25, BASE, 1.9]} speed={2}>
        <mesh position={[0, total / 2, 0]} material={toon(COLORS.pipe)}>
          <cylinderGeometry args={[0.12, 0.12, total, 10]} />
          <Edges color={INK} threshold={30} />
        </mesh>
        <mesh position={[0, total / 2, -0.6]} material={toon(COLORS.wire)}>
          <cylinderGeometry args={[0.06, 0.06, total, 8]} />
        </mesh>
        <Spark height={total} />
      </Grow>

      {/* Windows and door pop in as finishing progresses. */}
      {windows.map((w, k) => (
        <Grow key={k} to={s.finish >= (k + 1) / (windows.length + 1) ? 1 : 0} axes="xyz" position={w.pos} speed={5}>
          <Block size={w.size} color={w.door ? COLORS.wood : COLORS.glass} />
        </Grow>
      ))}

      {/* Solar water heaters / PV when green building applies. */}
      <Grow to={model.greenInstalled && s.green > 0 ? 1 : 0} axes="xyz" position={[0, BASE + total, -0.5]}>
        {[-2.4, 0, 2.4].map((x) => (
          <Block key={x} size={[1.8, 0.08, 1.4]} position={[x, 0.55, 0]} rotation={[-0.5, 0, 0]} color={COLORS.navy} />
        ))}
      </Grow>

      {/* Topping-out flag once the frame is complete. */}
      {structureUp && !model.complete && <Flag position={[W / 2 - 0.4, BASE + total, -D / 2 + 0.4]} />}

      {/* Scaffold along the front while the building goes up. */}
      <Grow to={showScaffold ? builtFloors / n : 0} position={[0, 0, D / 2 + 0.9]} speed={2}>
        <Scaffold height={total + BASE} />
      </Grow>
    </group>
  );
}

function Scaffold({ height }: { height: number }) {
  const levels = Math.max(1, Math.round(height / 1.5));
  return (
    <group>
      {[-W / 2, -W / 6, W / 6, W / 2].map((x) => (
        <Block key={x} size={[0.08, height, 0.08]} position={[x, 0, 0]} color="#94a3b8" edges={false} />
      ))}
      {Array.from({ length: levels }, (_, k) => (
        <group key={k}>
          <Block size={[W + 0.1, 0.06, 0.06]} position={[0, (k + 1) * 1.5, 0]} color="#94a3b8" edges={false} />
          <Block size={[W, 0.06, 0.6]} position={[0, (k + 1) * 1.5 - 0.06, -0.3]} color={COLORS.wood} />
        </group>
      ))}
    </group>
  );
}

/** A bright pulse travelling up the conduit: the electricity being tested. */
function Spark({ height }: { height: number }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.position.y = ((clock.elapsedTime * 2.2) % 1) * height;
  });
  return (
    <mesh ref={ref} position={[0, 0, -0.6]}>
      <sphereGeometry args={[0.13, 10, 8]} />
      <meshBasicMaterial color="#fde047" />
    </mesh>
  );
}

function Flag({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.rotation.y = Math.sin(clock.elapsedTime * 3) * 0.25;
  });
  return (
    <group position={position}>
      <Block size={[0.06, 2.4, 0.06]} color="#475569" edges={false} />
      <mesh ref={ref} position={[0.55, 2.05, 0]} material={toon("#ffffff")}>
        <boxGeometry args={[1.1, 0.7, 0.02]} />
        <Edges color={INK} />
        {[0.23, -0.23].map((y) => (
          <mesh key={y} position={[0, y, 0.015]}>
            <boxGeometry args={[1.1, 0.08, 0.01]} />
            <meshBasicMaterial color="#2563eb" />
          </mesh>
        ))}
      </mesh>
    </group>
  );
}
