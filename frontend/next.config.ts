import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/gcs/scans/:path*",
        destination: "https://storage.googleapis.com/screener-signals-carbonbridge/scans/:path*",
      },
      {
        source: "/api/gcs/signals/:path*",
        destination: "https://storage.googleapis.com/screener-signals-carbonbridge/signals/:path*",
      },
    ];
  },
};

export default nextConfig;
