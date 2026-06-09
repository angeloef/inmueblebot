import type { NextConfig } from 'next'
import path from 'path'

const nextConfig: NextConfig = {
  // Fix: monorepo with multiple lockfiles — pin the output tracing root to this package
  outputFileTracingRoot: path.join(__dirname, '../'),
}

export default nextConfig
