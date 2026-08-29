import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js and only the
  // node_modules actually traced as reachable. It is what lets the runtime
  // image skip `npm install` entirely.
  output: "standalone",

  images: {
    // `next/image` refuses an external host it has not been told about, and the
    // refusal happens at render rather than at build — so without this the
    // landing page compiles cleanly and then 500s on the first request.
    //
    // Narrowed to the exact host and path prefix Pexels serves photos from.
    // A wildcard hostname here would let any URL that reached a `src` prop be
    // proxied through this origin's image optimiser.
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.pexels.com",
        pathname: "/photos/**",
      },
    ],
  },
};

export default nextConfig;
