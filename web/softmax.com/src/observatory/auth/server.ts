import "server-only";

import { auth } from "@/lib/auth";
import { loadUserById } from "@/lib/user";

export async function getApiHeadersFromSession(): Promise<
  Record<string, string>
> {
  const session = await auth();
  let headers: Record<string, string> = {};
  const userId = session?.user?.id;
  if (userId) {
    const user = await loadUserById(userId);
    if (!user) {
      throw new Error(`User not found: ${userId}`);
    }
    headers = {
      "X-User-Id": userId,
      "X-User-Email": user.email ?? "",
      "X-User-Is-Softmax-Team-Member": user.isSoftmaxTeamMember
        ? "true"
        : "false",
      "X-Auth-Secret": process.env.OBSERVATORY_AUTH_SECRET ?? "",
    };
  }
  return headers;
}

export async function getAuthToken(): Promise<string | null> {
  return null; // TODO - observatory doesn't rely on tokens anymore, but this breaks tracing code
}
