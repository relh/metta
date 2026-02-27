import { NextRequest } from "next/server";

import { getApiHeadersFromSession } from "@/observatory/auth/server";

async function proxy(req: NextRequest, method: string, path: string) {
  const headers: Record<string, string> = {
    ...(await getApiHeadersFromSession()),
    ...Object.fromEntries(req.headers.entries()),
  };

  const url = new URL(`${process.env.OBSERVATORY_API_URL}/${path}`);
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  const contentType = req.headers.get("Content-Type");
  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  const response = await fetch(url, {
    method,
    redirect: "follow",
    headers,
    body: method === "POST" ? req.body : undefined,
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
