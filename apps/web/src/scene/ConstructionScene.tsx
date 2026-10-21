import { AnimatePresence, motion } from "motion/react";
import { useMemo } from "react";
import { Crane, Excavator, MixerTruck, Worker, useLoop, type Pose } from "./actors";
import type { SceneModel } from "./model";

// Scene geometry, in viewBox units (400 x 240).
const GY = 190; // ground line
const HX = 135; // building left edge
const W = 130; // building width
const MAST_X = 300;

const CONCRETE = "#a8a29e";
const BLOCK = "#d6cfc2";
const PLASTER = "#fffaf0";
const SOIL = "#8b6b4a";

const ease = { duration: 0.9, ease: [0.22, 1, 0.36, 1] } as const;
const pop = { type: "spring", stiffness: 160, damping: 14 } as const;

interface CrewMember {
  x: number;
  y: number;
  pose: Pose;
  flip?: boolean;
  range?: number;
}

export function ConstructionScene({
  model,
  label,
  className,
}: {
  model: SceneModel;
  label: string;
  className?: string;
}) {
  const loop = useLoop();
  const s = model.stage;
  const n = Math.min(Math.max(model.floors.length, 1), 4);
  const floorH = [46, 46, 40, 32, 26][n]!;
  const top = GY - n * floorH;
  const floorTop = (i: number) => GY - (i + 1) * floorH;
  const floors = model.floors.slice(0, n);

  const builtFloors = floors.filter((f) => f > 0).length;
  const builtTop = builtFloors ? floorTop(builtFloors - 1) : GY;
  const structureUp = floors.every((f) => f >= 1);
  const showCrane = s.foundations > 0 && !(structureUp && s.envelope >= 1);
  const showScaffold = builtFloors > 0 && s.finish < 0.6;
  const wallH = (GY - top) * Math.min(1, s.envelope * 1.25);
  const pipesOpacity = s.systems > 0 ? (s.finish >= 0.6 ? 0.12 : 0.9) : 0;
  const machine = model.complete
    ? null
    : model.focus === "foundations"
      ? "excavator"
      : model.focus === "skeleton" || model.focus === "mamad"
        ? "mixer"
        : null;

  const windows = useMemo(() => {
    const list: { x: number; y: number; w: number; h: number; door?: boolean }[] = [];
    for (let i = 0; i < n; i++) {
      const bottom = GY - i * floorH;
      if (i === 0) {
        list.push({ x: HX + W * 0.46, y: bottom - floorH * 0.66, w: 13, h: floorH * 0.66, door: true });
        list.push({ x: HX + W * 0.7, y: bottom - floorH * 0.7, w: 22, h: floorH * 0.38 });
      } else {
        list.push({ x: HX + W * 0.14, y: bottom - floorH * 0.72, w: 22, h: floorH * 0.4 });
        list.push({ x: HX + W * 0.44, y: bottom - floorH * 0.72, w: 22, h: floorH * 0.4 });
        list.push({ x: HX + W * 0.72, y: bottom - floorH * 0.72, w: 22, h: floorH * 0.4 });
      }
    }
    return list;
  }, [n, floorH]);

  const crew = crewFor(model, { n, floorH, top, builtTop, floorTop, showScaffold });
  const sunX = 30 + model.overall * 330;
  const sunY = 70 - Math.sin(model.overall * Math.PI) * 42;

  return (
    <svg
      viewBox="0 0 400 240"
      className={className}
      role="img"
      aria-label={label}
      preserveAspectRatio="xMidYMax slice"
    >
      <defs>
        <linearGradient id="scene-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#bfdbfe" />
          <stop offset="0.75" stopColor="#eff6ff" />
          <stop offset="1" stopColor="#fef3c7" />
        </linearGradient>
        <pattern id="lattice" width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="8" fill="none" stroke="#f59e0b" strokeWidth="1.4" />
          <path d="M0 0 8 8" stroke="#f59e0b" strokeWidth="0.9" />
        </pattern>
        <pattern id="scaffold" width="12" height="14" patternUnits="userSpaceOnUse">
          <rect width="12" height="14" fill="none" stroke="#94a3b8" strokeWidth="1" />
          <path d="M0 14 12 0" stroke="#cbd5e1" strokeWidth="0.7" />
        </pattern>
        <pattern id="rebar" width="6" height="6" patternUnits="userSpaceOnUse">
          <path d="M0 3h6M3 0v6" stroke="#b45309" strokeWidth="0.8" />
        </pattern>
        <clipPath id="scene-drum">
          <ellipse rx="14" ry="8" />
        </clipPath>
      </defs>

      {/* Sky, sun moving with overall progress, drifting clouds, distant town. */}
      <rect width="400" height="240" fill="url(#scene-sky)" />
      <motion.circle r={15} fill="#fcd34d" initial={false} animate={{ cx: sunX, cy: sunY }} transition={ease} />
      <motion.circle r={22} fill="#fcd34d" opacity={0.25} initial={false} animate={{ cx: sunX, cy: sunY }} transition={ease} />
      {[
        { y: 34, d: 46, s: 1 },
        { y: 62, d: 64, s: 0.7 },
      ].map((c, i) => (
        <motion.g key={i} initial={{ x: -90 + i * 200 }} {...loop({ x: [-90 + i * 200, 470, -90] }, { duration: c.d, ease: "linear", times: [0, 0.999, 1] })}>
          <g transform={`translate(0 ${c.y}) scale(${c.s})`} fill="#fff" opacity={0.9}>
            <ellipse cx={0} cy={0} rx={22} ry={8} />
            <ellipse cx={12} cy={-6} rx={13} ry={9} />
            <ellipse cx={-10} cy={-4} rx={10} ry={7} />
          </g>
        </motion.g>
      ))}
      <g fill="#c7d2e0">
        <rect x={6} y={138} width={26} height={52} />
        <rect x={34} y={120} width={18} height={70} />
        <rect x={56} y={146} width={30} height={44} />
        <rect x={330} y={128} width={22} height={62} />
        <rect x={356} y={112} width={20} height={78} />
        <rect x={378} y={150} width={22} height={40} />
      </g>

      {/* Ground. */}
      <rect y={GY} width="400" height={240 - GY} fill="#d6c4a0" />
      <rect y={GY} width="400" height="3" fill="#a3b18a" />

      {/* Before starting: permit sign and survey stakes. */}
      <g>
        <rect x={107} y={GY - 26} width={2.5} height={26} fill="#64748b" />
        <rect x={92} y={GY - 44} width={32} height={20} rx={2} fill="#fff" stroke="var(--color-brand)" strokeWidth={1.2} />
        <text x={108} y={GY - 36} textAnchor="middle" fontSize={7} fontWeight={700} fill="var(--color-brand)">
          היתר
        </text>
        <motion.path
          d={`M100 ${GY - 31} l4 3 8 -7`}
          fill="none"
          stroke="#16a34a"
          strokeWidth={1.8}
          strokeLinecap="round"
          initial={false}
          animate={{ pathLength: s.pre >= 1 ? 1 : 0, opacity: s.pre >= 1 ? 1 : 0 }}
          transition={ease}
        />
        <rect x={93} y={GY - 27.5} width={30 * s.pre} height={1.6} fill="#f59e0b" />
      </g>
      <AnimatePresence>
        {s.foundations < 0.3 && (
          <motion.g key="stakes" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <path d={`M${HX} ${GY - 3}H${HX + W}`} stroke="#ef4444" strokeWidth={0.6} strokeDasharray="3 2" />
            {[HX, HX + W].map((x) => (
              <g key={x}>
                <rect x={x - 1} y={GY - 10} width={2} height={10} fill="#a16207" />
                <path d={`M${x + 1} ${GY - 10}l5 2-5 2z`} fill="#f97316" />
              </g>
            ))}
          </motion.g>
        )}
      </AnimatePresence>

      {/* Foundations: dig the pit, tie rebar, pour the slab. */}
      <motion.rect
        x={HX - 10}
        y={GY}
        width={W + 20}
        height={16}
        fill={SOIL}
        style={{ originY: 0 }}
        initial={false}
        animate={{ scaleY: s.foundations > 0 && s.foundations < 1 ? 1 : 0 }}
        transition={ease}
      />
      <motion.rect
        x={HX - 6}
        y={GY + 2}
        width={W + 12}
        height={10}
        fill="url(#rebar)"
        initial={false}
        animate={{ opacity: s.foundations >= 0.5 && s.foundations < 1 ? 1 : 0 }}
        transition={ease}
      />
      <motion.rect
        x={HX - 4}
        y={GY - 4}
        width={W + 8}
        height={8}
        rx={1}
        fill={CONCRETE}
        style={{ originX: 0.5 }}
        initial={false}
        animate={{ scaleX: s.foundations >= 1 ? 1 : 0, opacity: s.foundations >= 1 ? 1 : 0 }}
        transition={pop}
      />

      {/* Skeleton, floor by floor: columns rise, formwork, slab. */}
      {floors.map((f, i) => {
        const y0 = floorTop(i);
        const columns = [HX + 2, HX + W / 3 - 3, HX + (2 * W) / 3 - 3, HX + W - 8];
        return (
          <g key={i}>
            {columns.map((cx) => (
              <motion.rect
                key={cx}
                x={cx}
                y={y0 + 4}
                width={6}
                height={floorH - 4}
                fill={CONCRETE}
                style={{ originY: 1 }}
                initial={false}
                animate={{ scaleY: Math.min(1, f * 1.6) }}
                transition={ease}
              />
            ))}
            {f > 0 && f < 1 && (
              <g stroke="#b45309" strokeWidth={0.7}>
                {columns.map((cx) => (
                  <path key={cx} d={`M${cx + 1.5} ${y0 + 4}v-6M${cx + 4.5} ${y0 + 4}v-6`} />
                ))}
              </g>
            )}
            <motion.rect
              x={HX - 4}
              y={y0}
              width={W + 8}
              height={5}
              fill="none"
              stroke="#a16207"
              strokeDasharray="4 2"
              initial={false}
              animate={{ opacity: f >= 0.4 && f < 1 ? 1 : 0 }}
            />
            <motion.rect
              x={HX - 4}
              y={y0}
              width={W + 8}
              height={5}
              rx={0.8}
              fill={CONCRETE}
              style={{ originX: 0 }}
              initial={false}
              animate={{ scaleX: f >= 1 ? 1 : 0 }}
              transition={pop}
            />
          </g>
        );
      })}

      {/* Protected room (mamad) on the ground floor. */}
      <motion.g initial={false} animate={{ opacity: s.mamad > 0 ? 1 : 0 }} transition={ease}>
        <rect x={HX + 8} y={GY - floorH + 5} width={34} height={floorH - 9} fill="#78716c" opacity={0.35 + s.mamad * 0.65} />
        <rect x={HX + 19} y={GY - floorH * 0.62} width={12} height={10} fill="#475569" stroke="#334155" strokeWidth={0.8} />
      </motion.g>

      {/* Envelope: walls rise, then plaster once finishing starts. */}
      <motion.rect
        x={HX}
        width={W}
        initial={false}
        animate={{ y: GY - wallH, height: wallH, fill: s.finish >= 0.3 ? PLASTER : BLOCK }}
        transition={ease}
      />
      {floors.map((f, i) =>
        f >= 1 && wallH > 0 ? (
          <rect key={i} x={HX - 4} y={floorTop(i)} width={W + 8} height={4} rx={0.8} fill={s.finish >= 0.3 ? "#e7e0d2" : CONCRETE} />
        ) : null,
      )}
      {s.mamad >= 1 && wallH >= floorH && (
        <g>
          <rect x={HX + 19} y={GY - floorH * 0.62} width={12} height={10} fill="#64748b" stroke="#334155" strokeWidth={0.8} />
          <path d={`M${HX + 25} ${GY - floorH * 0.62 + 2}l3 1.2v2.6c0 1.8-3 3-3 3s-3-1.2-3-3v-2.6z`} fill="#fbbf24" />
        </g>
      )}

      {/* Systems: water pipes and live wiring, hidden in the walls once finished. */}
      <motion.g initial={false} animate={{ opacity: pipesOpacity }} transition={ease}>
        <path d={`M${HX + W - 20} ${GY}V${top + 6}`} stroke="#3b82f6" strokeWidth={2.2} fill="none" />
        {floors.map((_, i) => (
          <path key={i} d={`M${HX + W - 20} ${floorTop(i) + floorH - 8}h-26`} stroke="#3b82f6" strokeWidth={1.6} />
        ))}
        <motion.path
          d={`M${HX + 56} ${GY}V${top + 8}H${HX + 100}`}
          stroke="#eab308"
          strokeWidth={1.4}
          strokeDasharray="4 3"
          fill="none"
          {...loop({ strokeDashoffset: [0, -14] }, { duration: 0.8, ease: "linear" })}
        />
      </motion.g>

      {/* Finishing: windows and door pop in one by one. */}
      {windows.map((w, k) => {
        const shown = s.finish >= (k + 1) / (windows.length + 1);
        return (
          <motion.g
            key={k}
            style={{ originX: 0.5, originY: 0.5 }}
            initial={false}
            animate={{ scale: shown ? 1 : 0, opacity: shown ? 1 : 0 }}
            transition={{ ...pop, delay: shown ? k * 0.06 : 0 }}
          >
            {w.door ? (
              <>
                <rect x={w.x} y={w.y} width={w.w} height={w.h} rx={1} fill="#92400e" />
                <circle cx={w.x + w.w - 3} cy={w.y + w.h / 2} r={0.9} fill="#fcd34d" />
              </>
            ) : (
              <>
                <rect x={w.x} y={w.y} width={w.w} height={w.h} rx={1} fill="#93c5fd" stroke="#fff" strokeWidth={1.4} />
                <path d={`M${w.x + 4} ${w.y + w.h - 3}l6 -${w.h - 6}`} stroke="#fff" strokeWidth={1} opacity={0.7} />
                <rect x={w.x - 2} y={w.y + w.h} width={w.w + 4} height={1.6} fill="#e7e0d2" />
              </>
            )}
          </motion.g>
        );
      })}

      {/* Roof waterproofing, topping-out flag, solar panels. */}
      <motion.rect
        x={HX - 4}
        y={top - 3}
        width={W + 8}
        height={3}
        fill="#334155"
        initial={false}
        animate={{ opacity: s.envelope >= 1 ? 1 : 0 }}
        transition={ease}
      />
      <AnimatePresence>
        {structureUp && !model.complete && (
          <motion.g key="flag" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={pop}>
            <rect x={HX + W - 10} y={top - 22} width={1.4} height={20} fill="#475569" />
            <motion.g style={{ originX: 0 }} {...loop({ skewY: [-6, 6, -6] }, { duration: 1.6 })}>
              <rect x={HX + W - 8.6} y={top - 22} width={14} height={9} fill="#fff" stroke="#cbd5e1" strokeWidth={0.3} />
              <rect x={HX + W - 8.6} y={top - 20.6} width={14} height={1.2} fill="#2563eb" />
              <rect x={HX + W - 8.6} y={top - 15.6} width={14} height={1.2} fill="#2563eb" />
            </motion.g>
          </motion.g>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {model.greenInstalled && s.green > 0 && (
          <motion.g key="solar" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={pop}>
            {[0, 1, 2].map((k) => (
              <path key={k} d={`M${HX + 14 + k * 26} ${top - 3}l6 -9h16l-4 9z`} fill="#1e3a8a" stroke="#93c5fd" strokeWidth={0.6} />
            ))}
          </motion.g>
        )}
      </AnimatePresence>

      {/* Scaffold beside the building while it goes up. */}
      <AnimatePresence>
        {showScaffold && (
          <motion.rect
            key="scaffold"
            x={HX + W + 4}
            width={12}
            fill="url(#scaffold)"
            initial={{ opacity: 0, y: GY, height: 0 }}
            animate={{ opacity: 1, y: builtTop - 6, height: GY - builtTop + 6 }}
            exit={{ opacity: 0 }}
            transition={ease}
          />
        )}
      </AnimatePresence>

      {/* Crane and machines. */}
      <AnimatePresence>
        {showCrane && (
          <motion.g key="crane" initial={{ x: 120, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 140, opacity: 0 }} transition={{ duration: 1.2, ease: "easeInOut" }}>
            <Crane mastX={MAST_X} groundY={GY} topY={32} />
          </motion.g>
        )}
      </AnimatePresence>
      <AnimatePresence mode="wait">
        {machine === "excavator" && (
          <motion.g key="excavator" initial={{ x: -80 }} animate={{ x: 0 }} exit={{ x: -100 }} transition={{ duration: 1.4, ease: "easeOut" }}>
            <Excavator x={40} y={GY + 2} />
          </motion.g>
        )}
        {machine === "mixer" && (
          <motion.g key="mixer" initial={{ x: -90 }} animate={{ x: 0 }} exit={{ x: -110 }} transition={{ duration: 1.4, ease: "easeOut" }}>
            <MixerTruck x={34} y={GY + 2} />
          </motion.g>
        )}
      </AnimatePresence>

      {/* Garden appears with finishing. */}
      {[
        { x: 28, h: 26 },
        { x: 372, h: 30 },
        { x: 120, h: 14 },
      ].map((t, k) => (
        <motion.g
          key={k}
          style={{ originX: 0.5, originY: 1 }}
          initial={false}
          animate={{ scale: s.finish >= 0.5 ? 1 : 0 }}
          transition={{ ...pop, delay: k * 0.12 }}
        >
          <rect x={t.x - 1.2} y={GY - t.h * 0.4} width={2.4} height={t.h * 0.4} fill="#92400e" />
          <circle cx={t.x} cy={GY - t.h * 0.62} r={t.h * 0.34} fill="#4d7c0f" />
          <circle cx={t.x + t.h * 0.18} cy={GY - t.h * 0.75} r={t.h * 0.24} fill="#65a30d" />
        </motion.g>
      ))}

      {/* The crew works wherever the next critical step is. */}
      <AnimatePresence mode="popLayout">
        {crew.map((c, k) => (
          <motion.g
            key={`${model.focus}-${model.focusFloor}-${k}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, delay: 0.3 + k * 0.15 }}
          >
            <Worker {...c} delay={k * 0.25} />
          </motion.g>
        ))}
      </AnimatePresence>

      {/* Form 4 stamp and confetti when everything is done. */}
      <AnimatePresence>
        {model.complete && (
          <motion.g key="stamp" initial={{ scale: 0, rotate: -40 }} animate={{ scale: 1, rotate: -12 }} exit={{ scale: 0 }} transition={{ ...pop, delay: 0.4 }} style={{ originX: 0.5, originY: 0.5 }}>
            <circle cx={62} cy={58} r={28} fill="#f59e0b" />
            <circle cx={62} cy={58} r={23} fill="none" stroke="#fff" strokeWidth={1.2} strokeDasharray="3 2" />
            <text x={62} y={66} textAnchor="middle" fontSize={26} fontWeight={800} fill="#fff" fontFamily="Rubik, sans-serif">
              4
            </text>
            <path d="M74 40l4 4 9-9" fill="none" stroke="#fff" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
          </motion.g>
        )}
      </AnimatePresence>
      {model.complete && <Confetti />}
    </svg>
  );
}

function crewFor(
  model: SceneModel,
  g: {
    n: number;
    floorH: number;
    top: number;
    builtTop: number;
    floorTop: (i: number) => number;
    showScaffold: boolean;
  },
): CrewMember[] {
  if (model.complete) {
    return [
      { x: HX - 22, y: GY, pose: "cheer" },
      { x: HX + W * 0.4, y: GY, pose: "cheer", flip: true },
      { x: HX + W + 24, y: GY, pose: "cheer", flip: true },
    ];
  }
  const groundFeet = GY - 4;
  switch (model.focus) {
    case "foundations":
      return [
        { x: HX + 36, y: GY + 12, pose: "shovel" },
        { x: HX + 96, y: GY + 12, pose: "shovel", flip: true },
      ];
    case "skeleton": {
      const floor = Math.min(Math.max((model.focusFloor ?? 1) - 1, 0), g.n - 1);
      const feet = floor === 0 ? groundFeet : g.floorTop(floor - 1);
      return [
        { x: HX + 26, y: feet, pose: "hammer" },
        { x: HX + 58, y: feet, pose: "walk", range: 44 },
      ];
    }
    case "mamad":
      return [{ x: HX + 50, y: groundFeet, pose: "drill", flip: true }];
    case "envelope":
      return [
        { x: HX + W + 10, y: g.showScaffold ? g.builtTop : groundFeet, pose: "hammer", flip: true },
        { x: HX - 60, y: GY, pose: "walk", range: 40 },
      ];
    case "systems":
      return [
        { x: HX + W - 36, y: groundFeet, pose: "drill" },
        { x: HX + 70, y: g.n > 1 ? g.floorTop(0) : groundFeet, pose: "clipboard" },
      ];
    case "finish":
      return [
        { x: HX + 34, y: GY, pose: "paint" },
        { x: HX + W - 30, y: GY, pose: "paint", flip: true },
      ];
    case "green":
      return [{ x: HX + 50, y: g.top - 3, pose: "hammer" }];
    case "form4":
      return [
        { x: HX - 26, y: GY, pose: "clipboard" },
        { x: HX + W + 26, y: GY, pose: "walk", range: -30 },
      ];
    case "pre":
    default:
      return [
        { x: 82, y: GY, pose: "clipboard" },
        { x: HX + 40, y: GY, pose: "walk", range: 50 },
      ];
  }
}

const CONFETTI_COLORS = ["#f59e0b", "#ef4444", "#3b82f6", "#22c55e", "#a855f7", "#fff"];

function Confetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => ({
        x: 200 + (Math.random() - 0.5) * 60,
        dx: (Math.random() - 0.5) * 340,
        dy: 120 + Math.random() * 90,
        rotate: Math.random() * 720,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length]!,
        delay: Math.random() * 1.6,
      })),
    [],
  );
  const loop = useLoop();
  return (
    <g>
      {pieces.map((p, i) => (
        <motion.rect
          key={i}
          x={p.x}
          y={40}
          width={3}
          height={5}
          fill={p.color}
          initial={{ opacity: 0 }}
          {...loop(
            { x: [0, p.dx * 0.4, p.dx], y: [0, -30, p.dy], rotate: [0, p.rotate], opacity: [0, 1, 0] },
            { duration: 3, delay: p.delay, ease: "easeOut" },
          )}
        />
      ))}
    </g>
  );
}
