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
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // The API is proxied same-origin, so the app needs no framing, sniffing, or
          // cross-origin referrer leakage. No CSP is set yet: Next's inline bootstrap
          // requires nonce plumbing, and a broken policy is worse than none.
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
