import { useReducedMotion } from "motion/react";
import { Component, Suspense, lazy, type ReactNode } from "react";
import { ConstructionScene } from "../scene/ConstructionScene";
import type { WorldProps } from "./World";

// three.js is large; load it only where a 3D world is shown.
const World = lazy(() => import("./World"));

const webgl = (() => {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
})();

/**
 * The 3D construction world, with the SVG scene as a stand-in while it loads and as the
 * fallback for no WebGL, reduced motion, or a rendering error.
 */
export function LiveWorld({ label, ...props }: WorldProps & { label: string }) {
  const reduce = useReducedMotion();
  const fallback = (
    <div className={props.className}>
      <ConstructionScene model={props.model} label={label} className="size-full" />
    </div>
  );
  if (!webgl || reduce) return fallback;
  return (
    <WorldBoundary fallback={fallback}>
      <Suspense fallback={fallback}>
        <World {...props} />
      </Suspense>
    </WorldBoundary>
  );
}

class WorldBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
