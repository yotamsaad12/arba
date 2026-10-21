import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import * as THREE from "three";
import type { SceneModel } from "../scene/model";
import { Crew } from "./Crew";
import { House, houseHeight } from "./House";
import { COLORS } from "./materials";
import type { Authority } from "./authorities";
import { Ground, MailRoutes, Neighbourhood, SiteMarkers, Sun, Tree } from "./Site";
import { Grow } from "./primitives";

const PAPER = "#f4f0e6";

export interface CameraKey {
  at: number;
  position: [number, number, number];
  target: [number, number, number];
}

export interface WorldProps {
  model: SceneModel;
  /** "orbit": slow drift around the house. "story": camera follows `progress` through `keys`. */
  camera: "orbit" | "story";
  progress?: RefObject<number>;
  keys?: CameraKey[];
  authorities: Authority[];
  focusLabel?: string;
  completeLabel?: string;
  /** Display classes for the focus chip, e.g. to hide it on small screens. */
  chipClassName?: string;
  className?: string;
}

export default function World(props: WorldProps) {
  const container = useRef<HTMLDivElement>(null);
  const visible = useInView(container);
  const labelRefs = useRef(new Map<string, HTMLDivElement>());
  const labels = useLabels(props);

  return (
    <div ref={container} className={props.className}>
      <div className="relative size-full">
        <Canvas
          frameloop={visible ? "always" : "never"}
          dpr={[1, 1.75]}
          shadows
          camera={{ fov: 34, near: 0.5, far: 260, position: [24, 14, 28] }}
          gl={{ antialias: true, powerPreference: "high-performance" }}
        >
          <color attach="background" args={[PAPER]} />
          <fog attach="fog" args={[PAPER, 55, 125]} />
          <hemisphereLight args={["#ffffff", "#e9e1cf", 1.6]} />
          <directionalLight
            position={[-14, 26, 18]}
            intensity={1.5}
            castShadow
            shadow-mapSize={[1024, 1024]}
            shadow-camera-left={-22}
            shadow-camera-right={22}
            shadow-camera-top={22}
            shadow-camera-bottom={-22}
          />
          <Scene {...props} />
          <LabelTracker labels={labels} refs={labelRefs} />
        </Canvas>
        {/* Labels are plain DOM in this tree, positioned every frame by LabelTracker. */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          {labels.map((label) => (
            <div
              key={label.key}
              ref={(el) => {
                if (el) labelRefs.current.set(label.key, el);
                else labelRefs.current.delete(label.key);
              }}
              // Physical left: the projected x is measured from the left edge, also in RTL.
              className="absolute top-0 opacity-0 will-change-transform"
              style={{ left: 0 }}
            >
              {label.content}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface Label {
  key: string;
  position: [number, number, number];
  content: ReactNode;
  /** Base size at a camera distance of ~26 units. */
  scale?: number;
}

function useLabels({ model, authorities, focusLabel, completeLabel, chipClassName }: WorldProps): Label[] {
  const top = houseHeight(model);
  const labels: Label[] = authorities.map((a) => ({
    key: `authority-${a.key}`,
    position: [a.position[0], 7.4, a.position[2]],
    scale: 0.85,
    content: (
      <div
        dir="rtl"
        className="whitespace-nowrap rounded-lg border-2 border-ink bg-surface px-2.5 py-1 font-display text-sm font-bold text-ink shadow-[3px_3px_0_0_var(--color-ink)]"
      >
        {a.label}
      </div>
    ),
  }));
  if (focusLabel && !model.complete) {
    labels.push({
      key: "focus",
      position: [0, top + 2.6, 0],
      content: (
        <div
          dir="rtl"
          className={`${chipClassName ?? "flex"} items-center gap-2 whitespace-nowrap rounded-xl border-2 border-ink bg-surface px-3 py-1.5 font-display text-base font-bold text-ink shadow-[4px_4px_0_0_var(--color-ink)]`}
        >
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex size-2.5 rounded-full bg-accent" />
          </span>
          {focusLabel}
        </div>
      ),
    });
  }
  if (model.complete && completeLabel) {
    labels.push({
      key: "stamp",
      position: [0, top + 4, 0],
      scale: 1.1,
      content: (
        <div className="grid size-28 animate-[stamp_0.6s_cubic-bezier(0.34,1.56,0.64,1)_both] place-items-center rounded-full border-4 border-dashed border-white bg-accent font-display text-white shadow-[5px_5px_0_0_var(--color-ink)]">
          <div className="text-center leading-none">
            <div className="text-5xl font-extrabold">4</div>
            <div className="mt-1 text-xs font-bold">{completeLabel}</div>
          </div>
        </div>
      ),
    });
  }
  return labels;
}

/** Projects each label's world position to the screen and moves its DOM node there. */
function LabelTracker({ labels, refs }: { labels: Label[]; refs: RefObject<Map<string, HTMLDivElement>> }) {
  const { camera, size } = useThree();
  const point = useMemo(() => new THREE.Vector3(), []);
  const latest = useRef(labels);
  latest.current = labels;
  useFrame(() => {
    for (const label of latest.current) {
      const el = refs.current.get(label.key);
      if (!el) continue;
      point.fromArray(label.position);
      const distance = camera.position.distanceTo(point);
      point.project(camera);
      if (point.z > 1) {
        el.style.opacity = "0";
        continue;
      }
      const x = ((point.x + 1) / 2) * size.width;
      const y = ((1 - point.y) / 2) * size.height;
      const scale = THREE.MathUtils.clamp((26 / distance) * (label.scale ?? 1), 0.45, 1.25);
      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${scale})`;
      el.style.opacity = "1";
    }
  });
  return null;
}

function Scene({ model, camera, progress, keys, authorities }: WorldProps) {
  const top = houseHeight(model);
  return (
    <>
      {camera === "orbit" ? <OrbitRig target={top / 2} /> : <StoryRig progress={progress} keys={keys ?? []} />}
      <Sun position={[-34, 30, -60]} />
      <Ground />
      <Neighbourhood />
      <SiteMarkers model={model} />
      <House model={model} />
      <Crew model={model} />
      <MailRoutes model={model} authorities={authorities} />
      {[
        [-6.5, 0, -5],
        [-7, 0, 4.6],
        [6.8, 0, -4.5],
      ].map((p, k) => (
        <Grow key={k} to={model.stage.finish >= 0.5 ? 1 : 0} axes="xyz" position={p as [number, number, number]} delay={k * 0.2}>
          <Tree position={[0, 0, 0]} scale={0.9} />
        </Grow>
      ))}
      {model.complete && <Confetti height={top + 6} />}
    </>
  );
}

/** Slow drift around the house, nudged by the pointer for a bit of parallax. */
function OrbitRig({ target }: { target: number }) {
  const { camera, pointer } = useThree();
  const look = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ clock }, dt) => {
    const t = clock.elapsedTime;
    const angle = 0.6 + Math.sin(t * 0.07) * 0.35 + pointer.x * 0.12;
    const radius = 30;
    const goal = new THREE.Vector3(Math.sin(angle) * radius, 12 + pointer.y * 2, Math.cos(angle) * radius);
    camera.position.lerp(goal, 1 - Math.exp(-dt * 2));
    look.set(0, target, 0);
    camera.lookAt(look);
  });
  return null;
}

/** Camera that travels between keyframes as the page scrolls. */
function StoryRig({ progress, keys }: { progress?: RefObject<number>; keys: CameraKey[] }) {
  const { camera, pointer, size } = useThree();
  const pos = useMemo(() => new THREE.Vector3(), []);
  const tgt = useMemo(() => new THREE.Vector3(), []);
  const right = useMemo(() => new THREE.Vector3(), []);
  const look = useRef(new THREE.Vector3(0, 3, 0));
  // Story cards sit on the right on wide screens (RTL) and at the bottom on phones;
  // pan so the house lands in the free part of the screen.
  const wide = size.width >= 1024;
  useFrame((_, dt) => {
    if (!keys.length) return;
    const p = THREE.MathUtils.clamp(progress?.current ?? 0, 0, 1);
    let i = keys.findIndex((k) => k.at >= p);
    if (i <= 0) i = i === 0 ? 1 : keys.length - 1;
    const a = keys[i - 1]!;
    const b = keys[i]!;
    const local = THREE.MathUtils.smootherstep((p - a.at) / Math.max(b.at - a.at, 0.0001), 0, 1);
    pos.fromArray(a.position).lerp(tgt.fromArray(b.position), local);
    tgt.fromArray(a.target).lerp(new THREE.Vector3().fromArray(b.target), local);
    const distance = pos.distanceTo(tgt);
    right.subVectors(tgt, pos).cross(camera.up).normalize();
    if (wide) {
      pos.addScaledVector(right, distance * 0.22);
      tgt.addScaledVector(right, distance * 0.22);
    } else {
      // Narrow screens: step back so the house fits, and look lower so it sits above the card.
      pos.sub(tgt).multiplyScalar(1.8).add(tgt);
      tgt.y -= distance * 0.16;
    }
    pos.x += pointer.x * 1.2;
    pos.y += pointer.y * 0.8;
    const k = 1 - Math.exp(-dt * 3);
    camera.position.lerp(pos, k);
    look.current.lerp(tgt, k);
    camera.lookAt(look.current);
  });
  return null;
}

const CONFETTI = ["#f59e0b", "#ef4444", "#3b82f6", "#22c55e", "#a855f7", "#ffffff"];

function Confetti({ height }: { height: number }) {
  const count = 160;
  const ref = useRef<THREE.InstancedMesh>(null);
  const pieces = useMemo(
    () =>
      Array.from({ length: count }, () => ({
        x: (Math.random() - 0.5) * 22,
        z: (Math.random() - 0.5) * 18,
        speed: 1.5 + Math.random() * 2,
        spin: Math.random() * 6,
        offset: Math.random() * 10,
      })),
    [],
  );
  const dummy = useMemo(() => new THREE.Object3D(), []);
  useEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const color = new THREE.Color();
    pieces.forEach((_, i) => mesh.setColorAt(i, color.set(CONFETTI[i % CONFETTI.length]!)));
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [pieces]);
  useFrame(({ clock }) => {
    const mesh = ref.current;
    if (!mesh) return;
    const t = clock.elapsedTime;
    pieces.forEach((p, i) => {
      const fall = ((t * p.speed + p.offset) % (height + 2)) ;
      dummy.position.set(p.x + Math.sin(t + p.offset) * 0.8, height - fall, p.z);
      dummy.rotation.set(t * p.spin, t * p.spin * 0.7, 0);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]}>
      <planeGeometry args={[0.28, 0.42]} />
      <meshBasicMaterial side={THREE.DoubleSide} color={COLORS.paper} />
    </instancedMesh>
  );
}

function useInView(ref: RefObject<HTMLElement | null>) {
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setInView(!!entry?.isIntersecting), {
      rootMargin: "100px",
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return inView;
}
