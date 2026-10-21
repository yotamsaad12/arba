import { motion, useReducedMotion, type TargetAndTransition, type Transition } from "motion/react";

const VEST = "#f97316";
const HAT = "#facc15";
const SKIN = "#e8b48f";
const PANTS = "#1e3a5f";

/** Repeating animation that switches itself off for people who prefer reduced motion. */
export function useLoop() {
  const reduce = useReducedMotion();
  return (animate: TargetAndTransition, transition: Transition) =>
    reduce
      ? {}
      : {
          animate,
          transition: { repeat: Infinity, ease: "easeInOut", ...transition } as Transition,
        };
}

export type Pose = "hammer" | "shovel" | "walk" | "clipboard" | "paint" | "cheer" | "drill";

/** A worker standing with feet at (x, y). About 20 units tall. */
export function Worker({
  x,
  y,
  pose,
  flip = false,
  delay = 0,
  range = 30,
}: {
  x: number;
  y: number;
  pose: Pose;
  flip?: boolean;
  delay?: number;
  /** Walking distance for the "walk" pose. */
  range?: number;
}) {
  const loop = useLoop();

  const body = (
    <g>
      <rect x={-3.2} y={-7.5} width={2.6} height={7.5} rx={1.2} fill={PANTS} />
      <rect x={0.6} y={-7.5} width={2.6} height={7.5} rx={1.2} fill={PANTS} />
      <rect x={-3.8} y={-16} width={7.6} height={9.5} rx={2.2} fill={VEST} />
      <rect x={-3.8} y={-12.6} width={7.6} height={1.3} fill="#fde68a" />
      <circle cx={0} cy={-19.2} r={3} fill={SKIN} />
      <path d="M-3.6 -19.8a3.6 3.6 0 0 1 7.2 0z" fill={HAT} />
      <rect x={-4.4} y={-20.2} width={8.8} height={1.1} rx={0.55} fill="#eab308" />
    </g>
  );

  const arm = (() => {
    switch (pose) {
      case "hammer":
        return (
          <motion.g
            style={{ originX: 0, originY: 0 }}
            {...loop({ rotate: [-55, 15, -55] }, { duration: 0.7, delay })}
          >
            <line x1={0} y1={0} x2={6} y2={3} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <line x1={6} y1={3} x2={9} y2={-1} stroke="#7c4a1e" strokeWidth={1.2} />
            <rect x={7.5} y={-3} width={4} height={2.4} rx={0.5} fill="#64748b" />
          </motion.g>
        );
      case "drill":
        return (
          <motion.g {...loop({ x: [0, 0.6, 0] }, { duration: 0.12, delay })}>
            <line x1={0} y1={0} x2={5} y2={1} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <rect x={4.5} y={-1.5} width={5} height={3} rx={0.8} fill="#2563eb" />
            <line x1={9.5} y1={0} x2={12} y2={0} stroke="#94a3b8" strokeWidth={0.8} />
          </motion.g>
        );
      case "paint":
        return (
          <motion.g {...loop({ y: [3, -7, 3] }, { duration: 1.4, delay })}>
            <line x1={0} y1={0} x2={5} y2={-2} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <line x1={5} y1={-2} x2={7} y2={-7} stroke="#475569" strokeWidth={0.9} />
            <rect x={5} y={-10} width={5} height={3} rx={1.2} fill="#fffaf0" stroke="#cbd5e1" strokeWidth={0.4} />
          </motion.g>
        );
      case "clipboard":
        return (
          <g>
            <line x1={0} y1={0} x2={4} y2={3} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <rect x={3} y={-1} width={5} height={6.5} rx={0.6} fill="#fff" stroke="#94a3b8" strokeWidth={0.5} />
            <line x1={4} y1={1.2} x2={7} y2={1.2} stroke="#94a3b8" strokeWidth={0.4} />
            <line x1={4} y1={2.8} x2={7} y2={2.8} stroke="#94a3b8" strokeWidth={0.4} />
          </g>
        );
      case "shovel":
        return (
          <g>
            <line x1={0} y1={0} x2={5} y2={4} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <line x1={-2} y1={-2} x2={9} y2={10} stroke="#7c4a1e" strokeWidth={1.1} />
            <path d="M8 9l4 1-1 4-4-1z" fill="#64748b" />
          </g>
        );
      case "cheer":
        return (
          <g>
            <line x1={0} y1={0} x2={3} y2={-8} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <line x1={-7.6} y1={0} x2={-10.6} y2={-8} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
          </g>
        );
      case "walk":
        return (
          <g>
            <line x1={0} y1={0} x2={3} y2={5} stroke={SKIN} strokeWidth={2} strokeLinecap="round" />
            <rect x={1.5} y={4.5} width={7} height={2} rx={0.5} fill="#a16207" />
          </g>
        );
    }
  })();

  const figure = (
    <g transform={flip ? "scale(-1 1)" : undefined}>
      {body}
      <g transform="translate(3.8 -14)">{arm}</g>
    </g>
  );

  let motionProps = {};
  if (pose === "shovel") motionProps = loop({ y: [0, 1.6, 0], rotate: [0, 6, 0] }, { duration: 1, delay });
  if (pose === "cheer") motionProps = loop({ y: [0, -5, 0] }, { duration: 0.6, delay });
  if (pose === "walk") {
    motionProps = loop(
      { x: [0, range, range, 0, 0], scaleX: [1, 1, -1, -1, 1] },
      { duration: Math.max(3, range / 8), times: [0, 0.48, 0.5, 0.98, 1], ease: "linear", delay },
    );
  }

  return (
    <g transform={`translate(${x} ${y})`}>
      <motion.g style={{ originX: 0.5, originY: 1 }} {...motionProps}>
        {figure}
      </motion.g>
    </g>
  );
}

export function Excavator({ x, y }: { x: number; y: number }) {
  const loop = useLoop();
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={0} y={-6} width={34} height={6} rx={3} fill="#334155" />
      {[4, 12, 20, 28].map((cx) => (
        <circle key={cx} cx={cx + 1} cy={-3} r={2} fill="#64748b" />
      ))}
      <rect x={4} y={-17} width={22} height={11} rx={2} fill="#f59e0b" />
      <rect x={16} y={-26} width={11} height={10} rx={2} fill="#f59e0b" />
      <rect x={18} y={-24} width={7} height={5} rx={1} fill="#bae6fd" />
      {/* motion's CSS transform would replace a transform attribute, so position in a parent. */}
      <g transform="translate(26 -14)">
        <motion.g
          style={{ originX: 0, originY: 1 }}
          {...loop({ rotate: [-10, 20, -10] }, { duration: 2.4 })}
        >
          <path d="M0 0 18 -14" stroke="#d97706" strokeWidth={3.5} strokeLinecap="round" />
          <motion.g
            {...loop({ rotate: [0, 35, 0] }, { duration: 2.4 })}
            style={{ originX: 0, originY: 0 }}
          >
            <path d="M18 -14 26 -2" stroke="#d97706" strokeWidth={3} strokeLinecap="round" />
            <path d="M23 -3h7l-2 6h-6z" fill="#475569" />
          </motion.g>
        </motion.g>
      </g>
    </g>
  );
}

export function MixerTruck({ x, y }: { x: number; y: number }) {
  const loop = useLoop();
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={0} y={-12} width={44} height={7} rx={1.5} fill="#475569" />
      <rect x={32} y={-22} width={13} height={11} rx={2} fill="#1e3a5f" />
      <rect x={35} y={-20} width={7} height={5} rx={1} fill="#bae6fd" />
      <g transform="translate(15 -19)">
        <ellipse rx={14} ry={8} fill="#e2e8f0" stroke="#94a3b8" strokeWidth={0.6} />
        <g clipPath="url(#scene-drum)">
          <motion.g {...loop({ x: [-8, 0] }, { duration: 0.8, ease: "linear" })}>
            <path
              d="M-14 -8 -6 8M-6 -8 2 8M2 -8 10 8M10 -8 18 8"
              stroke="#f59e0b"
              strokeWidth={2}
            />
          </motion.g>
        </g>
      </g>
      {[8, 22, 38].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy={-4} r={4} fill="#1f2937" />
          <circle cx={cx} cy={-4} r={1.6} fill="#94a3b8" />
        </g>
      ))}
    </g>
  );
}

/** Tower crane with a trolley that carries a steel beam back and forth over the building. */
export function Crane({ mastX, groundY, topY }: { mastX: number; groundY: number; topY: number }) {
  const loop = useLoop();
  const jibStart = mastX - 150;
  return (
    <g>
      <rect x={mastX} y={topY} width={8} height={groundY - topY} fill="url(#lattice)" />
      <rect x={mastX - 6} y={groundY - 4} width={20} height={4} fill="#475569" />
      <rect x={jibStart} y={topY - 6} width={mastX + 40 - jibStart} height={5} fill="url(#lattice)" />
      <rect x={mastX + 26} y={topY - 2} width={14} height={9} rx={1} fill="#64748b" />
      <rect x={mastX - 3} y={topY - 14} width={14} height={9} rx={1.5} fill="#f59e0b" />
      <rect x={mastX - 1} y={topY - 12} width={6} height={4} rx={0.8} fill="#bae6fd" />
      <path
        d={`M${mastX + 4} ${topY - 22} L${jibStart + 10} ${topY - 6} M${mastX + 4} ${topY - 22} L${mastX + 36} ${topY - 6}`}
        stroke="#d97706"
        strokeWidth={0.8}
      />
      <rect x={mastX + 2} y={topY - 24} width={4} height={10} fill="#d97706" />
      <motion.g {...loop({ x: [0, -85, 0] }, { duration: 9 })}>
        <rect x={mastX - 32} y={topY - 2} width={10} height={3} fill="#334155" />
        <motion.g {...loop({ scaleY: [1, 1.6, 1] }, { duration: 4.5 })} style={{ originY: 0 }}>
          <line x1={mastX - 27} y1={topY + 1} x2={mastX - 27} y2={topY + 34} stroke="#334155" strokeWidth={0.6} />
        </motion.g>
        <motion.g {...loop({ y: [0, 20, 0], rotate: [-4, 4, -4] }, { duration: 4.5 })}>
          <path d={`M${mastX - 27} ${topY + 34}v4`} stroke="#334155" strokeWidth={1} />
          <rect x={mastX - 40} y={topY + 38} width={26} height={4} rx={0.6} fill="#ea580c" />
        </motion.g>
      </motion.g>
    </g>
  );
}
