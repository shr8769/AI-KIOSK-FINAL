/** @type {import('next').NextConfig} */
const fs = require('fs');
const path = require('path');

// Dynamically resolve active ngrok tunnel hostname if available
const dynamicOrigins = [
  'localhost:3000',
  '127.0.0.1:3000',
  '*.ngrok-free.app',
  '*.ngrok.app',
  '*.ngrok.io',
];

try {
  const tunnelFile = path.join(__dirname, 'public', 'tunnel.json');
  if (fs.existsSync(tunnelFile)) {
    const content = JSON.parse(fs.readFileSync(tunnelFile, 'utf8'));
    if (content.publicUrl) {
      const parsedHost = new URL(content.publicUrl).host;
      if (parsedHost && !dynamicOrigins.includes(parsedHost)) {
        dynamicOrigins.push(parsedHost);
      }
    }
  }
} catch (e) {}

const nextConfig = {
  allowedDevOrigins: dynamicOrigins,
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
    ];
  },
  devIndicators: {
    buildActivity: false,
  },
};

module.exports = nextConfig;
