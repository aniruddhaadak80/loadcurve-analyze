/** @type {import('next').NextConfig} */
// Next's postinstall lockfile patch walks *up* from this directory looking for a lockfile, and
// a `yarn.lock` vendored inside a transitive dependency sits above it. Next then concludes the
// project uses yarn and shells out to yarn 1.x, which fails the build wherever corepack is
// unset. This repo is an npm workspace with a committed `package-lock.json`, so the patch has
// nothing to correct and is skipped explicitly.
process.env.NEXT_IGNORE_INCORRECT_LOCKFILE ??= '1'

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
}

export default nextConfig
