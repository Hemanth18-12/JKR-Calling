/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@jkr/ui", "@jkr/sdk", "@jkr/contracts"],
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
