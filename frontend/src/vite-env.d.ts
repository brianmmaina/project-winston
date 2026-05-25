/** Vite env typing for compile-time guards on `import.meta.env`. */

/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_PROXY_TARGET?: string;
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
