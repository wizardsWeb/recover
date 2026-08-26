import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js and only the
  // node_modules actually traced as reachable. It is what lets the runtime
  // image skip `npm install` entirely.
  output: "standalone",
};

export default nextConfig;
