/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PRODUCT_TO_MCP_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
