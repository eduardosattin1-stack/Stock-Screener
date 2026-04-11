import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/gcs/:path*",
        destination: "https://storage.googleapis.com/screener-signals-carbonbridge/:path*",
      },
    ];
  },
};

export default nextConfig;
