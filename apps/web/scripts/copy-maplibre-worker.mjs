// MapLibre 6 runs its map work in a module worker that bundlers don't emit, so the worker and the
// module it imports are served as static files instead (lib/map/load-maplibre.ts points
// MapLibre at them). Copied from the installed package on every dev start and build, so they
// always match its version; public/maplibre/ is gitignored.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/package.json")) + "/dist";
const target = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "maplibre");

mkdirSync(target, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(dist, file), join(target, file));
}
