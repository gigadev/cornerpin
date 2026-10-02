// Placeholder app icons, drawn at build time by app/icons/[file]/route.tsx until there is a brand.
export const ICONS = {
  "icon-192.png": { size: 192, maskable: false },
  "icon-512.png": { size: 512, maskable: false },
  "icon-maskable-512.png": { size: 512, maskable: true },
  "apple-touch-icon.png": { size: 180, maskable: true },
} as const;

export type IconFile = keyof typeof ICONS;

export function iconFiles(): IconFile[] {
  return Object.keys(ICONS) as IconFile[];
}

export function isIconFile(file: string): file is IconFile {
  return Object.hasOwn(ICONS, file);
}
