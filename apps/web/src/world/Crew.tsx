import { Edges, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type ReactNode } from "react";
import * as THREE from "three";
import type { SceneModel } from "../scene/model";
import { HOUSE, floorsShown, houseHeight } from "./House";
import { COLORS, INK, latticeTexture, toon } from "./materials";
import { Block, Grow } from "./primitives";

type Vec3 = [number, number, number];
export type Pose = "hammer" | "drill" | "paint" | "shovel" | "cheer" | "clipboard" | "walk";

interface CrewMember {
  position: Vec3;
  pose: Pose;
  /** Rotation around Y. 0 faces +z (towards the street), PI faces the house front. */
  facing?: number;
  /** Walking distance for "walk". */
  range?: number;
}

/** A construction worker about 1.8 units tall, feet at the group origin. */
export function Worker({ position, pose, facing = 0, range = 4, phase = 0 }: CrewMember & { phase?: number }) {
  const root = useRef<THREE.Group>(null);
  const body = useRef<THREE.Group>(null);
  const arm = useRef<THREE.Group>(null);
  const otherArm = useRef<THREE.Group>(null);
  const legs = useRef<(THREE.Group | null)[]>([]);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime + phase;
    const r = root.current;
    const a = arm.current;
    const b = body.current;
    if (!r || !a || !b) return;
    let swing = 0;
    switch (pose) {
      case "hammer":
        a.rotation.x = -1.1 - Math.abs(Math.sin(t * 5)) * 1.3;
        break;
      case "drill":
        a.rotation.x = -1.5;
        b.position.x = Math.sin(t * 60) * 0.015;
        break;
      case "paint":
        a.rotation.x = -2.4 + Math.sin(t * 2.4) * 0.6;
        break;
      case "shovel":
        b.rotation.x = 0.25 + Math.sin(t * 3) * 0.3;
        a.rotation.x = -0.9;
        break;
      case "cheer":
        r.position.y = position[1] + Math.abs(Math.sin(t * 5)) * 0.45;
        a.rotation.x = -2.9;
        if (otherArm.current) otherArm.current.rotation.x = -2.9;
        break;
      case "clipboard":
        a.rotation.x = -0.9;
        b.rotation.x = Math.sin(t * 1.5) * 0.06;
        break;
      case "walk": {
        // Ping-pong along the local x axis, turning around at each end.
        const cycle = (t * 1.1) / Math.max(Math.abs(range), 0.1);
        const p = cycle % 2;
        const forward = p < 1;
        const x = (forward ? p : 2 - p) * range;
        r.position.x = position[0] + Math.cos(facing) * x;
        r.position.z = position[2] - Math.sin(facing) * x;
        r.rotation.y = facing + (forward ? Math.PI / 2 : -Math.PI / 2) * Math.sign(range || 1);
        swing = Math.sin(t * 9) * 0.55;
        a.rotation.x = -swing * 0.8;
        b.position.y = Math.abs(Math.sin(t * 9)) * 0.05;
        break;
      }
    }
    legs.current[0]?.rotation.set(swing, 0, 0);
    legs.current[1]?.rotation.set(-swing, 0, 0);
  });

  const tool: ReactNode = {
    hammer: (
      <group position={[0, -0.62, 0.08]}>
        <Block size={[0.05, 0.4, 0.05]} color={COLORS.wood} edges={false} />
        <Block size={[0.22, 0.1, 0.1]} position={[0, 0.36, 0]} color="#64748b" />
      </group>
    ),
    drill: <Block size={[0.14, 0.18, 0.4]} position={[0, -0.7, 0.15]} color="#2563eb" />,
    paint: (
      <group position={[0, -0.62, 0]}>
        <Block size={[0.04, 0.5, 0.04]} color="#475569" edges={false} />
        <Block size={[0.4, 0.12, 0.14]} position={[0, -0.12, 0]} color={COLORS.plaster} />
      </group>
    ),
    shovel: (
      <group position={[0, -0.6, 0.1]} rotation={[0.6, 0, 0]}>
        <Block size={[0.05, 1, 0.05]} position={[0, -0.6, 0]} color={COLORS.wood} edges={false} />
        <Block size={[0.26, 0.3, 0.04]} position={[0, -0.85, 0]} color="#64748b" />
      </group>
    ),
    clipboard: <Block size={[0.3, 0.4, 0.03]} position={[0, -0.75, 0.14]} color="#ffffff" />,
    walk: <Block size={[0.5, 0.2, 0.3]} position={[0, -0.7, 0.18]} color={COLORS.block} />,
    cheer: null,
  }[pose];

  return (
    <group ref={root} position={position} rotation={[0, facing, 0]}>
      <group ref={body}>
        {[-0.12, 0.12].map((x, k) => (
          <group key={x} position={[x, 0.82, 0]} ref={(g) => void (legs.current[k] = g)}>
            <Block size={[0.18, 0.82, 0.22]} position={[0, -0.82, 0]} color={COLORS.navy} />
          </group>
        ))}
        <Block size={[0.52, 0.7, 0.32]} position={[0, 0.8, 0]} color={COLORS.orange} />
        <Block size={[0.53, 0.07, 0.33]} position={[0, 1.08, 0]} color="#fde68a" edges={false} />
        <mesh position={[0, 1.7, 0]} material={toon(COLORS.skin)}>
          <sphereGeometry args={[0.17, 14, 10]} />
        </mesh>
        <mesh position={[0, 1.76, 0]} material={toon(COLORS.hat)}>
          <sphereGeometry args={[0.2, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <Edges color={INK} threshold={40} />
        </mesh>
        <mesh position={[0, 1.76, 0.04]} material={toon(COLORS.hat)}>
          <cylinderGeometry args={[0.25, 0.25, 0.03, 16]} />
        </mesh>
        <group ref={arm} position={[0.33, 1.44, 0]}>
          <Block size={[0.13, 0.6, 0.15]} position={[0, -0.6, 0]} color={COLORS.orange} />
          {tool}
        </group>
        <group ref={otherArm} position={[-0.33, 1.44, 0]}>
          <Block size={[0.13, 0.6, 0.15]} position={[0, -0.6, 0]} color={COLORS.orange} />
        </group>
      </group>
    </group>
  );
}

/** Drives a vehicle in from the side when `show`, and away again when not. */
function Arrive({ show, at, children }: { show: boolean; at: Vec3; children: ReactNode }) {
  const ref = useRef<THREE.Group>(null);
  const offstage = at[0] - 30;
  useFrame((_, dt) => {
    const g = ref.current;
    if (!g) return;
    g.position.x = THREE.MathUtils.damp(g.position.x, show ? at[0] : offstage, 1.4, Math.min(dt, 0.1));
    g.visible = g.position.x > offstage + 1;
  });
  return (
    <group ref={ref} position={[offstage, at[1], at[2]]} visible={false}>
      {children}
    </group>
  );
}

function Excavator() {
  const boom = useRef<THREE.Group>(null);
  const stick = useRef<THREE.Group>(null);
  const upper = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (boom.current) boom.current.rotation.z = -0.35 + Math.sin(t * 1.3) * 0.3;
    if (stick.current) stick.current.rotation.z = -1.1 + Math.sin(t * 1.3 + 0.8) * 0.45;
    if (upper.current) upper.current.rotation.y = Math.sin(t * 0.45) * 0.5;
  });
  return (
    <group>
      <Block size={[3.2, 0.7, 2]} color="#3f4652" />
      <group ref={upper} position={[0, 0.7, 0]}>
        <Block size={[2.4, 1, 1.8]} position={[-0.3, 0, 0]} color={COLORS.amber} />
        <Block size={[1.1, 1.2, 1.1]} position={[0.4, 1, 0.3]} color={COLORS.amber} />
        <Block size={[0.05, 0.6, 0.8]} position={[0.96, 1.3, 0.3]} color={COLORS.glass} edges={false} />
        <group ref={boom} position={[0.9, 0.8, -0.3]}>
          <Block size={[2.6, 0.32, 0.3]} position={[1.3, -0.16, 0]} color={COLORS.amberDark} />
          <group ref={stick} position={[2.5, 0, 0]}>
            <Block size={[1.8, 0.26, 0.26]} position={[0.9, -0.13, 0]} color={COLORS.amberDark} />
            <Block size={[0.6, 0.5, 0.7]} position={[1.9, -0.3, 0]} color="#475569" />
          </group>
        </group>
      </group>
    </group>
  );
}

function MixerTruck() {
  const drum = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    if (drum.current) drum.current.rotation.x += dt * 2.2;
  });
  return (
    <group>
      <Block size={[4.6, 0.5, 1.8]} position={[0, 0.5, 0]} color="#64748b" />
      <Block size={[1.3, 1.4, 1.8]} position={[1.85, 1, 0]} color={COLORS.navy} />
      <Block size={[0.05, 0.6, 1.4]} position={[2.52, 1.6, 0]} color={COLORS.glass} edges={false} />
      <group position={[-0.6, 1.8, 0]} rotation={[0, 0, 0.18]}>
        <group ref={drum} rotation={[0, 0, Math.PI / 2]}>
          <mesh material={toon("#e8e4da")}>
            <cylinderGeometry args={[0.6, 0.95, 2.8, 14, 1]} />
            <Edges color={INK} threshold={10} />
          </mesh>
          {[-0.7, 0, 0.7].map((y) => (
            <mesh key={y} position={[0, y, 0]} rotation={[0, y, 0.3]} material={toon(COLORS.amber)}>
              <torusGeometry args={[0.82 - y * 0.12, 0.05, 6, 20]} />
            </mesh>
          ))}
        </group>
      </group>
      {[-1.5, 0, 1.6].map((x) =>
        [-0.9, 0.9].map((z) => (
          <mesh key={`${x}${z}`} position={[x, 0.42, z]} rotation={[Math.PI / 2, 0, 0]} material={toon("#1f2937")}>
            <cylinderGeometry args={[0.42, 0.42, 0.3, 14]} />
            <Edges color="#000" threshold={30} />
          </mesh>
        )),
      )}
    </group>
  );
}

/** Tower crane: slews over the house, trolley runs along the jib, beam swings on the hook. */
function Crane({ height }: { height: number }) {
  const top = useRef<THREE.Group>(null);
  const trolley = useRef<THREE.Group>(null);
  const cable = useRef<THREE.Mesh>(null);
  const load = useRef<THREE.Group>(null);
  const mastMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        map: latticeTexture(1, Math.round(height / 0.9)),
        transparent: true,
        alphaTest: 0.4,
        side: THREE.DoubleSide,
      }),
    [height],
  );
  const jibMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        map: latticeTexture(22, 1),
        transparent: true,
        alphaTest: 0.4,
        side: THREE.DoubleSide,
      }),
    [],
  );
  // Point the jib (local -x) at the house, then slew around that heading.
  const heading = Math.atan2(5, 9.5);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (top.current) top.current.rotation.y = heading + Math.sin(t * 0.22) * 0.55;
    const reach = 4 + ((Math.sin(t * 0.35) + 1) / 2) * 9;
    const drop = 5 + Math.sin(t * 0.7) * 2.2;
    if (trolley.current) trolley.current.position.x = -reach;
    if (cable.current) {
      cable.current.scale.y = drop;
      cable.current.position.y = -drop / 2;
    }
    if (load.current) {
      load.current.position.y = -drop - 0.2;
      load.current.rotation.y = Math.sin(t * 0.9) * 0.4;
      load.current.rotation.z = Math.sin(t * 1.4) * 0.05;
    }
  });

  return (
    <group>
      <Block size={[2.4, 0.6, 2.4]} color={COLORS.concrete} />
      <mesh position={[0, height / 2, 0]} material={mastMaterial}>
        <boxGeometry args={[0.9, height, 0.9]} />
      </mesh>
      <group ref={top} position={[0, height, 0]}>
        <Block size={[1.3, 1.1, 1.3]} position={[0, -1.1, 0.9]} color={COLORS.amber} />
        <mesh position={[-8, 0.35, 0]} material={jibMaterial}>
          <boxGeometry args={[16, 0.7, 0.7]} />
        </mesh>
        <mesh position={[2.6, 0.35, 0]} material={jibMaterial}>
          <boxGeometry args={[5.2, 0.7, 0.7]} />
        </mesh>
        <Block size={[1.4, 1.2, 1.1]} position={[4.4, -0.9, 0]} color={COLORS.concreteDark} />
        <Block size={[0.35, 3, 0.35]} position={[0, 0.7, 0]} color={COLORS.amberDark} />
        <Line points={[[0, 3.7, 0], [-15.5, 0.7, 0]]} color={INK} lineWidth={1} />
        <Line points={[[0, 3.7, 0], [4.8, 0.7, 0]]} color={INK} lineWidth={1} />
        <group ref={trolley} position={[-8, 0, 0]}>
          <Block size={[0.8, 0.3, 0.9]} position={[0, -0.3, 0]} color="#334155" />
          <mesh ref={cable} material={toon("#334155")}>
            <cylinderGeometry args={[0.03, 0.03, 1, 4]} />
          </mesh>
          <group ref={load}>
            <Block size={[0.3, 0.3, 0.3]} position={[0, 0.2, 0]} color={COLORS.amber} />
            <Block size={[3.4, 0.28, 0.36]} position={[0, -0.1, 0]} color="#c2410c" />
          </group>
        </group>
      </group>
    </group>
  );
}

export function Crew({ model }: { model: SceneModel }) {
  const s = model.stage;
  const floors = model.floors.slice(0, floorsShown(model));
  const structureUp = floors.every((f) => f >= 1);
  const showCrane = s.foundations > 0 && !(structureUp && s.envelope >= 1);
  const crew = useMemo(() => crewFor(model), [model]);

  return (
    <group>
      <Grow to={showCrane ? 1 : 0} position={[9.5, 0, -5]} speed={1.6}>
        <Crane height={Math.max(14, houseHeight(model) + 8)} />
      </Grow>
      <Arrive show={!model.complete && model.focus === "foundations"} at={[-10, 0, 1.5]}>
        <Excavator />
      </Arrive>
      <Arrive
        show={!model.complete && (model.focus === "skeleton" || model.focus === "mamad")}
        at={[-10.5, 0, 5]}
      >
        <MixerTruck />
      </Arrive>
      {crew.map((c, k) => (
        <Worker key={`${model.focus}-${model.focusFloor}-${model.complete}-${k}`} {...c} phase={k * 0.7} />
      ))}
    </group>
  );
}

function crewFor(model: SceneModel): CrewMember[] {
  const { base, floorH, depth, width } = HOUSE;
  const front = depth / 2;
  const facingHouse = Math.PI;
  if (model.complete) {
    return [
      { position: [-3, 0, front + 3], pose: "cheer", facing: 0.3 },
      { position: [0.5, 0, front + 3.5], pose: "cheer" },
      { position: [3.5, 0, front + 3], pose: "cheer", facing: -0.3 },
    ];
  }
  switch (model.focus) {
    case "foundations":
      return [
        { position: [-2.5, 0.02, 1.2], pose: "shovel", facing: 0.6 },
        { position: [2.2, 0.02, -1], pose: "shovel", facing: -2.2 },
      ];
    case "skeleton": {
      const n = floorsShown(model);
      const floor = Math.min(Math.max((model.focusFloor ?? 1) - 1, 0), n - 1);
      const y = base + floor * floorH;
      return [
        { position: [-2, y, 1], pose: "hammer", facing: -0.4 },
        { position: [0.5, y, -1.4], pose: "walk", range: 3 },
      ];
    }
    case "mamad":
      return [{ position: [-0.4, base, -1.2], pose: "drill", facing: -Math.PI / 2 }];
    case "envelope":
      return [
        { position: [2, Math.min(1.5, floorH), front + 0.75], pose: "hammer", facing: facingHouse },
        { position: [-9, 0, 7], pose: "walk", range: 4 },
      ];
    case "systems":
      return [
        { position: [width / 2 + 1, 0, 0.8], pose: "drill", facing: -Math.PI / 2 },
        { position: [-4, 0, front + 2.5], pose: "clipboard", facing: facingHouse + 0.4 },
      ];
    case "finish":
      return [
        { position: [-2.4, 0, front + 0.7], pose: "paint", facing: facingHouse },
        { position: [2.6, 0, front + 0.7], pose: "paint", facing: facingHouse },
      ];
    case "green":
      return [{ position: [-1, houseHeight(model), 0.6], pose: "hammer", facing: 0 }];
    case "form4":
      return [
        { position: [-5, 0, front + 2.5], pose: "clipboard", facing: facingHouse + 0.6 },
        { position: [2, 0, front + 4], pose: "walk", range: 3 },
      ];
    case "pre":
    default:
      return [
        { position: [-6.5, 0, front + 2.5], pose: "clipboard", facing: facingHouse + 0.8 },
        { position: [-2, 0, front + 1.5], pose: "walk", range: 4 },
      ];
  }
}
