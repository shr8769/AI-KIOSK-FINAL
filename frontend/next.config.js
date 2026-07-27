/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://127.0.0.1:8000/api/v1/:path*', // Proxy to Backend
      },
      {
        source: '/ws/admin/:path*',
        destination: 'http://127.0.0.1:8000/ws/admin/:path*', // Admin WebSocket proxy
      },
    ]
  },
};
module.exports = nextConfig;
