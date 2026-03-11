import createMDX from "@next/mdx";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  pageExtensions: ["js", "jsx", "md", "mdx", "ts", "tsx"],
  images: {
    qualities: [75, 100],
    remotePatterns: [
      {
        protocol: "https",
        hostname: "softmax-public.s3.amazonaws.com",
        pathname: "/softmax-com/images/**",
      },
    ],
  },
  async redirects() {
    return [
      {
        source: "/alb",
        destination: "/alignmentleague",
        permanent: false,
      },
      {
        source: "/alb/:path*",
        destination: "/",
        permanent: false,
      },
      {
        source: "/privacy-policy.pdf",
        destination: "/privacy",
        permanent: true,
      },
      {
        source: "/inspiration",
        destination: "/blog/inspiration",
        permanent: true,
      },
    ];
  },
};

const withMDX = createMDX({
  extension: /\.(md|mdx)$/,
  options: {
    remarkPlugins: ["remark-smartypants"],
  },
});

export default withMDX(nextConfig);
