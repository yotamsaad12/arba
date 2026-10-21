import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

interface Burst {
  id: number;
  x: number;
  y: number;
}
interface Toast {
  id: number;
  text: string;
  icon: string;
}

interface CelebrationApi {
  /** Confetti from a screen point, e.g. the button that was pressed. */
  burst: (x: number, y: number) => void;
  toast: (text: string, icon?: string) => void;
}

const Context = createContext<CelebrationApi>({ burst: () => {}, toast: () => {} });

const COLORS = ["#f59e0b", "#ef4444", "#3b82f6", "#22c55e", "#a855f7", "#172033"];

export function CelebrationProvider({ children }: { children: ReactNode }) {
  const [bursts, setBursts] = useState<Burst[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const burst = useCallback((x: number, y: number) => {
    const id = ++nextId.current;
    setBursts((b) => [...b, { id, x, y }]);
    window.setTimeout(() => setBursts((b) => b.filter((item) => item.id !== id)), 1400);
  }, []);

  const toast = useCallback((text: string, icon = "🎉") => {
    const id = ++nextId.current;
    setToasts((t) => [...t.slice(-2), { id, text, icon }]);
    window.setTimeout(() => setToasts((t) => t.filter((item) => item.id !== id)), 3200);
  }, []);

  const api = useMemo(() => ({ burst, toast }), [burst, toast]);

  return (
    <Context.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-0 z-50">
        {bursts.map((b) => (
          <ConfettiBurst key={b.id} x={b.x} y={b.y} />
        ))}
      </div>
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex flex-col items-center gap-2 px-4">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 30, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 380, damping: 26 }}
              className="flex items-center gap-2 rounded-full border-2 border-ink bg-surface px-4 py-2.5 font-display font-bold shadow-[4px_4px_0_0_var(--color-ink)]"
              role="status"
            >
              <span className="text-xl">{t.icon}</span>
              {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Context.Provider>
  );
}

function ConfettiBurst({ x, y }: { x: number; y: number }) {
  const pieces = useMemo(
    () =>
      Array.from({ length: 22 }, (_, i) => {
        const angle = (i / 22) * Math.PI * 2 + Math.random() * 0.4;
        const distance = 50 + Math.random() * 70;
        return {
          dx: Math.cos(angle) * distance,
          dy: Math.sin(angle) * distance - 30,
          rotate: Math.random() * 540 - 270,
          color: COLORS[i % COLORS.length],
          round: i % 3 === 0,
        };
      }),
    [],
  );
  return (
    <>
      {pieces.map((p, i) => (
        <motion.span
          key={i}
          className={p.round ? "absolute size-2 rounded-full" : "absolute h-2.5 w-1.5 rounded-[1px]"}
          style={{ left: x, top: y, backgroundColor: p.color }}
          initial={{ x: 0, y: 0, opacity: 1, rotate: 0, scale: 0.6 }}
          animate={{ x: p.dx, y: [0, p.dy, p.dy + 60], opacity: [1, 1, 0], rotate: p.rotate, scale: 1 }}
          transition={{ duration: 1.2, ease: "easeOut", times: [0, 0.5, 1] }}
        />
      ))}
    </>
  );
}

export function useCelebrate() {
  return useContext(Context);
}
