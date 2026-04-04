/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow large .docx uploads (max 25 MB)
  api: {
    bodyParser: false,
  },
  experimental: {
    serverActions: {
      bodySizeLimit: "25mb",
    },
  },
};

module.exports = nextConfig;
