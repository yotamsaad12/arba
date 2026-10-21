import * as THREE from "three";

/** Ink color for outlines: the "drawn" look. */
export const INK = "#23262d";

export const COLORS = {
  paper: "#fbf8f1",
  ground: "#f1ecdf",
  concrete: "#d7d1c3",
  concreteDark: "#a8a196",
  block: "#e3dac8",
  plaster: "#fffaf0",
  soil: "#c9b28c",
  amber: "#f59e0b",
  amberDark: "#d97706",
  orange: "#f97316",
  navy: "#1e3a5f",
  glass: "#bfdcf7",
  wood: "#9a6b3f",
  skin: "#e8b48f",
  hat: "#facc15",
  leaf: "#dfe8cf",
  pipe: "#5b8def",
  wire: "#eab308",
} as const;

// Three tones of light, so surfaces read like a flat illustration rather than plastic.
const gradientMap = (() => {
  const texture = new THREE.DataTexture(new Uint8Array([110, 190, 255]), 3, 1, THREE.RedFormat);
  texture.minFilter = THREE.NearestFilter;
  texture.magFilter = THREE.NearestFilter;
  texture.needsUpdate = true;
  return texture;
})();

const cache = new Map<string, THREE.MeshToonMaterial>();

/** Shared cel-shaded material per color. */
export function toon(color: string): THREE.MeshToonMaterial {
  let material = cache.get(color);
  if (!material) {
    material = new THREE.MeshToonMaterial({ color, gradientMap });
    cache.set(color, material);
  }
  return material;
}

function canvasTexture(size: number, draw: (ctx: CanvasRenderingContext2D) => void) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  draw(canvas.getContext("2d")!);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

/** Diagonal pen hatching on paper, for the ground and the building lot. */
export function hatchTexture(background: string, line: string, spacing = 10, width = 1.4) {
  return canvasTexture(128, (ctx) => {
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, 128, 128);
    ctx.strokeStyle = line;
    ctx.lineWidth = width;
    for (let i = -128; i < 256; i += spacing) {
      ctx.beginPath();
      ctx.moveTo(i, 128);
      ctx.lineTo(i + 128, 0);
      ctx.stroke();
    }
  });
}

/** Steel lattice for the crane: a square frame with a cross brace. Transparent between bars. */
export function latticeTexture(repeatX: number, repeatY: number) {
  const texture = canvasTexture(64, (ctx) => {
    ctx.clearRect(0, 0, 64, 64);
    ctx.strokeStyle = COLORS.amber;
    ctx.lineWidth = 7;
    ctx.strokeRect(3.5, 3.5, 57, 57);
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(4, 60);
    ctx.lineTo(60, 4);
    ctx.stroke();
  });
  texture.repeat.set(repeatX, repeatY);
  return texture;
}
