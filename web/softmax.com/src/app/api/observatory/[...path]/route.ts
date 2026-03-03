import { NextRequest } from "next/server";

import { getApiHeadersFromSession } from "@/observatory/auth/server";

const HOP_BY_HOP_HEADERS = new Set([
  "host",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-length",
  "accept-encoding",
  "upgrade",
]);

async function proxy(req: NextRequest, method: string, path: string) {
  const headers: Record<string, string> = {
    ...(await getApiHeadersFromSession()),
  };
  for (const [key, value] of req.headers.entries()) {
    if (!HOP_BY_HOP_HEADERS.has(key)) {
      headers[key] = value;
    }
  }

  const url = new URL(`${process.env.OBSERVATORY_API_URL}/${path}`);
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  const body = method === "POST" ? await req.text() : undefined;

  const response = await fetch(url, {
    method,
    redirect: "follow",
    headers,
    body,
    cache: "no-store",
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type":
        response.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxy(req, "GET", (await params).path.join("/"));
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxy(req, "POST", (await params).path.join("/"));
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxy(req, "DELETE", (await params).path.join("/"));
}
