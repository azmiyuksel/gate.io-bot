import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
      {
        source: "/health/ready",
        destination: `${backendUrl}/health/ready`,
      },
      {
        source: "/debug/config",
        destination: `${backendUrl}/debug/config`,
      },
      {
        source: "/metrics",
        destination: `${backendUrl}/metrics`,
      },
    ];
  },
};

export default nextConfig;
