import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Three.js requires transpilation when imported as ESM
  transpilePackages: ["three", "@react-three/fiber", "@react-three/drei"],

  // Allow images from any HTTPS source (for future team logos)
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**" },
    ],
  },

  // Environment variable pass-through (set in .env.local or Amplify env)
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "",
    NEXT_PUBLIC_WS_URL:  process.env.NEXT_PUBLIC_WS_URL  ?? "",
    NEXT_PUBLIC_AWS_REGION: process.env.NEXT_PUBLIC_AWS_REGION ?? "us-east-1",
  },
}

export default nextConfig
