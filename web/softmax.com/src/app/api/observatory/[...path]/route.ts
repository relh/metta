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

const DEFAULT_OBSERVATORY_API_URL =
  "https://api.observatory.softmax-research.net";

function getObservatoryApiBaseUrl(): string {
  const configured = process.env.OBSERVATORY_API_URL?.trim();
  return configured || DEFAULT_OBSERVATORY_API_URL;
}

async function proxy(req: NextRequest, method: string, path: string) {
  const headers: Record<string, string> = {
    ...(await getApiHeadersFromSession()),
  };
  for (const [key, value] of req.headers.entries()) {
    if (!HOP_BY_HOP_HEADERS.has(key)) {
      headers[key] = value;
    }
  }

  let url: URL;
  try {
    const base = getObservatoryApiBaseUrl().replace(/\/+$/, "");
    const normalizedPath = path.replace(/^\/+/, "");
    url = new URL(`${base}/${normalizedPath}`);
  } catch (error) {
    console.error("Invalid Observatory API URL configuration", error);
    return Response.json(
      { error: "Observatory API is not configured correctly." },
      { status: 500 },
    );
  }
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  const body = method === "POST" ? await req.text() : undefined;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      redirect: "follow",
      headers,
      body,
      cache: "no-store",
    });
  } catch (error) {
    console.error("Failed to proxy Observatory API request", error);
    return Response.json(
      { error: "Failed to reach Observatory API upstream." },
      { status: 502 },
    );
  }

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
