import { registerOTel } from "@vercel/otel";

export function register() {
  const propagateContextUrls = process.env.OBSERVATORY_API_URL
    ? [new URL(process.env.OBSERVATORY_API_URL).hostname]
    : [];

  registerOTel({
    serviceName: "softmax-com",
    instrumentationConfig: {
      fetch: { propagateContextUrls },
    },
  });
}
