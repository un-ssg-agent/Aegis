// Proxy the API calls to the FastAPI backend (monitor/app.py) so the browser
// hits same-origin paths and we avoid CORS. Override with BACKEND_URL if needed.
const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
export default {
  async rewrites() {
    return [
      { source: "/assess", destination: `${BACKEND}/assess` },
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
    ];
  },
};
