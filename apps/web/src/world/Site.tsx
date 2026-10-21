import { Billboard, Edges, Instance, Instances, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { SceneModel } from "../scene/model";
import { AUTHORITY_SPOTS, type Authority } from "./authorities";
import { HOUSE, houseHeight } from "./House";
import { COLORS, INK, hatchTexture, toon } from "./materials";
import { Block, GableRoof, Grow } from "./primitives";

type Vec3 = [number, number, number];

// Deterministic pseudo-random, so the neighbourhood looks the same on every render.
function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export function Ground() {
  const ground = useMemo(() => {
    const t = hatchTexture(COLORS.ground, "rgba(35,38,45,0.09)", 9, 1.2);
    t.repeat.set(60, 60);
    return t;
  }, []);
  const lot = useMemo(() => {
    const t = hatchTexture("#ece4d1", "rgba(35,38,45,0.22)", 7, 1.4);
    t.repeat.set(8, 7);
    return t;
  }, []);

  const lotOutline = useMemo(() => roundedRect(17, 14, 2.2), []);
  const path = useMemo(
    () => [new THREE.Vector3(0.2, 0.03, 7), new THREE.Vector3(0.6, 0.03, 11), new THREE.Vector3(-1, 0.03, 16), new THREE.Vector3(-0.5, 0.03, 24)],
    [],
  );

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[240, 240]} />
        <meshToonMaterial map={ground} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]} receiveShadow>
        <planeGeometry args={[17, 14]} />
        <meshToonMaterial map={lot} />
      </mesh>
      <Line points={lotOutline} color={COLORS.amber} lineWidth={2.2} dashed dashSize={0.7} gapSize={0.45} />
      <Line points={new THREE.CatmullRomCurve3(path).getPoints(40)} color={COLORS.amber} lineWidth={2.5} dashed dashSize={0.5} gapSize={0.6} />
    </group>
  );
}

function roundedRect(w: number, d: number, r: number): Vec3[] {
  const pts: Vec3[] = [];
  const corners: [number, number, number][] = [
    [w / 2 - r, d / 2 - r, 0],
    [-w / 2 + r, d / 2 - r, Math.PI / 2],
    [-w / 2 + r, -d / 2 + r, Math.PI],
    [w / 2 - r, -d / 2 + r, (3 * Math.PI) / 2],
  ];
  for (const [cx, cz, start] of corners) {
    for (let k = 0; k <= 8; k++) {
      const a = start + (k / 8) * (Math.PI / 2);
      pts.push([cx + Math.cos(a) * r, 0.03, cz + Math.sin(a) * r]);
    }
  }
  pts.push(pts[0]!);
  return pts;
}

/** Sketched houses and trees around the lot, so the site sits in a street. */
export function Neighbourhood() {
  const { houses, trees } = useMemo(() => {
    const rand = seeded(7);
    const houses: { pos: Vec3; size: Vec3; roof: boolean; rot: number }[] = [];
    // Kept behind and beside the lot: the cameras look in from the front.
    const spots: Vec3[] = [
      [-20, 0, -4], [-31, 0, 7], [24, 0, -3], [21, 0, -11], [-8, 0, -20], [8, 0, -22], [-26, 0, -26], [30, 0, -24], [-34, 0, -8], [36, 0, 6],
    ];
    for (const pos of spots) {
      const w = 6 + rand() * 3;
      houses.push({ pos, size: [w, 3 + Math.floor(rand() * 2) * 3, 5 + rand() * 2], roof: rand() > 0.45, rot: (rand() - 0.5) * 0.3 });
    }
    const trees: { pos: Vec3; scale: number }[] = [];
    for (let k = 0; k < 46; k++) {
      const a = rand() * Math.PI * 2;
      const dist = 12 + rand() * 30;
      const pos: Vec3 = [Math.cos(a) * dist, 0, Math.sin(a) * dist - 4];
      // Cameras look in from the front and sides; keep trees behind the house or far away.
      if (pos[2] > -4 && dist < 30) continue;
      const blocked = [...houses.map((h) => h.pos), ...AUTHORITY_SPOTS];
      if (blocked.some((b) => Math.hypot(b[0] - pos[0], b[2] - pos[2]) < 5.5)) continue;
      trees.push({ pos, scale: 0.7 + rand() * 0.8 });
    }
    return { houses, trees };
  }, []);

  return (
    <group>
      {houses.map((h, k) => (
        <group key={k} position={h.pos} rotation={[0, h.rot, 0]}>
          <Block size={h.size} color={COLORS.paper} />
          {h.roof ? (
            <GableRoof width={h.size[0] + 0.4} depth={h.size[2] + 0.4} height={2} position={[0, h.size[1], 0]} color="#efe6d6" />
          ) : (
            <Block size={[h.size[0] + 0.3, 0.4, h.size[2] + 0.3]} position={[0, h.size[1], 0]} color={COLORS.paper} />
          )}
          {[-h.size[0] / 4, h.size[0] / 4].map((x) => (
            <Block key={x} size={[1.2, 1, 0.05]} position={[x, 1, h.size[2] / 2 + 0.03]} color="#dbe7f3" />
          ))}
        </group>
      ))}
      {trees.map((t, k) => (
        <Tree key={k} position={t.pos} scale={t.scale} />
      ))}
    </group>
  );
}

export function Tree({ position, scale = 1 }: { position: Vec3; scale?: number }) {
  return (
    <group position={position} scale={scale}>
      <Block size={[0.3, 1.4, 0.3]} color={COLORS.wood} />
      <mesh position={[0, 2.4, 0]} material={toon(COLORS.leaf)} castShadow>
        <dodecahedronGeometry args={[1.3, 0]} />
        <Edges color={INK} threshold={28} />
      </mesh>
      <mesh position={[0.55, 3.15, 0.2]} material={toon("#eef3e4")} castShadow>
        <dodecahedronGeometry args={[0.8, 0]} />
        <Edges color={INK} threshold={28} />
      </mesh>
    </group>
  );
}

/** Hand-drawn sun: an ink circle with rays, always facing the camera. */
export function Sun({ position }: { position: Vec3 }) {
  const rays = useMemo(() => {
    const segments: Vec3[][] = [];
    for (let k = 0; k < 36; k++) {
      const a = (k / 36) * Math.PI * 2;
      const r1 = 5.6;
      const r2 = k % 2 ? 6.6 : 7.4;
      segments.push([
        [Math.cos(a) * r1, Math.sin(a) * r1, 0],
        [Math.cos(a) * r2, Math.sin(a) * r2, 0],
      ]);
    }
    return segments;
  }, []);
  const circle = useMemo(
    () => Array.from({ length: 65 }, (_, k) => [Math.cos((k / 64) * Math.PI * 2) * 5, Math.sin((k / 64) * Math.PI * 2) * 5, 0] as Vec3),
    [],
  );
  const ref = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.rotation.z = clock.elapsedTime * 0.03;
  });
  return (
    <Billboard position={position}>
      <mesh>
        <circleGeometry args={[5, 48]} />
        <meshBasicMaterial color="#fdf6e3" />
      </mesh>
      <Line points={circle} color={INK} lineWidth={1.4} />
      <group ref={ref}>
        {rays.map((r, k) => (
          <Line key={k} points={r} color={INK} lineWidth={1} />
        ))}
      </group>
    </Billboard>
  );
}

/** Permit sign at the front of the lot, and survey stakes until foundations start. */
export function SiteMarkers({ model }: { model: SceneModel }) {
  const { width: W, depth: D } = HOUSE;
  const stakes: Vec3[] = [
    [-W / 2, 0, -D / 2],
    [W / 2, 0, -D / 2],
    [W / 2, 0, D / 2],
    [-W / 2, 0, D / 2],
  ];
  return (
    <group>
      <group position={[-6.8, 0, 6]} rotation={[0, 0.35, 0]}>
        <Block size={[0.15, 1.6, 0.15]} position={[-0.8, 0, 0]} color={COLORS.wood} edges={false} />
        <Block size={[0.15, 1.6, 0.15]} position={[0.8, 0, 0]} color={COLORS.wood} edges={false} />
        <Block size={[2.4, 1.5, 0.1]} position={[0, 1.5, 0]} color="#ffffff" />
        <Block size={[2.4 * Math.max(model.stage.pre, 0.02), 0.16, 0.12]} position={[-1.2 + 1.2 * Math.max(model.stage.pre, 0.02), 1.6, 0.02]} color={COLORS.amber} edges={false} />
      </group>
      <Grow to={model.stage.foundations < 0.3 ? 1 : 0} speed={3}>
        {stakes.map((p, k) => (
          <group key={k} position={p}>
            <Block size={[0.1, 0.8, 0.1]} color={COLORS.wood} edges={false} />
            <Block size={[0.3, 0.2, 0.02]} position={[0.15, 0.6, 0]} color={COLORS.orange} edges={false} />
          </group>
        ))}
        <Line points={[...stakes.map((p) => [p[0], 0.35, p[2]] as Vec3), [stakes[0]![0], 0.35, stakes[0]![2]]]} color="#ef4444" lineWidth={1.2} dashed dashSize={0.3} gapSize={0.2} />
      </Grow>
    </group>
  );
}

/**
 * Approving authorities around the site with mail flying to and from the house along dotted
 * arcs: the correspondence Arba manages.
 */
export function MailRoutes({ model, authorities }: { model: SceneModel; authorities: Authority[] }) {
  const roof = houseHeight(model) + 0.8;
  const curves = useMemo(
    () =>
      authorities.map((a) => {
        const start = new THREE.Vector3(a.position[0], 6, a.position[2]);
        const end = new THREE.Vector3(0, Math.max(roof, 2.5), 0);
        const mid = start.clone().lerp(end, 0.5);
        mid.y += 7;
        return new THREE.QuadraticBezierCurve3(start, mid, end);
      }),
    [authorities, roof],
  );

  return (
    <group>
      {authorities.map((a, k) => (
        <group key={a.key}>
          <group position={a.position}>
            <Block size={[4.5, 5.2, 4]} color={COLORS.paper} />
            <Block size={[5, 0.5, 4.5]} position={[0, 5.2, 0]} color={COLORS.navy} />
            {[-1.2, 0, 1.2].map((x) => (
              <Block key={x} size={[0.7, 3, 0.05]} position={[x, 1, 2.03]} color="#dbe7f3" />
            ))}
          </group>
          {/* Curves are in world space, so these sit outside the positioned group. */}
          <Trail curve={curves[k]!} />
          <Envelope curve={curves[k]!} offset={k * 0.37} />
        </group>
      ))}
    </group>
  );
}

function Trail({ curve }: { curve: THREE.Curve<THREE.Vector3> }) {
  const points = useMemo(() => curve.getSpacedPoints(46), [curve]);
  return (
    <Instances limit={points.length} material={toon(COLORS.amber)}>
      <sphereGeometry args={[0.11, 8, 6]} />
      {points.map((p, i) => (
        <Instance key={i} position={[p.x, p.y, p.z]} scale={0.6 + (i / points.length) * 0.9} />
      ))}
    </Instances>
  );
}

/** A letter flying along a mail route, back and forth. */
function Envelope({ curve, offset }: { curve: THREE.Curve<THREE.Vector3>; offset: number }) {
  const ref = useRef<THREE.Group>(null);
  const look = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ clock }) => {
    const g = ref.current;
    if (!g) return;
    const cycle = (clock.elapsedTime * 0.11 + offset) % 2;
    const t = cycle < 1 ? cycle : 2 - cycle;
    const p = curve.getPointAt(THREE.MathUtils.smootherstep(t, 0, 1));
    g.position.copy(p);
    g.position.y += Math.sin(clock.elapsedTime * 6 + offset * 10) * 0.12;
    curve.getTangentAt(Math.min(0.999, Math.max(0.001, t)), look);
    if (cycle >= 1) look.negate();
    g.lookAt(p.x + look.x, p.y + look.y, p.z + look.z);
  });
  return (
    <group ref={ref}>
      <mesh material={toon("#ffffff")} rotation={[0, Math.PI / 2, 0]}>
        <boxGeometry args={[1.1, 0.7, 0.06]} />
        <Edges color={INK} />
      </mesh>
      <Line
        points={[[0.04, 0.34, -0.54], [0.04, -0.02, 0], [0.04, 0.34, 0.54]]}
        color={COLORS.amberDark}
        lineWidth={1.6}
      />
    </group>
  );
}
