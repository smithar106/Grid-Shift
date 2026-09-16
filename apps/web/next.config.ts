import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle so the Railway image stays small.
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // Recharts and the solver-adjacent data layer are client-only; keep server bundles lean.
    optimizePackageImports: ["recharts"],
  },
};

export default nextConfig;
