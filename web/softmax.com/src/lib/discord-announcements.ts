import "server-only";

import type { Account, Profile, User } from "next-auth";

type DiscordField = {
  name: string;
  value: string;
  inline?: boolean;
};

function getWebhookUrl(): string | null {
  const value = process.env.DISCORD_ANNOUNCEMENTS_WEBHOOK_URL?.trim();
  return value ? value : null;
}

function getSiteUrl(): string {
  return (
    process.env.SITE_URL ??
    process.env.AUTH_URL ??
    process.env.NEXTAUTH_URL ??
    "https://softmax.com"
  ).replace(/\/$/, "");
}

async function sendDiscordAnnouncement(payload: {
  title: string;
  description: string;
  fields: DiscordField[];
}): Promise<void> {
  const webhookUrl = getWebhookUrl();
  if (!webhookUrl) {
    console.info(
      "DISCORD_ANNOUNCEMENTS_WEBHOOK_URL not configured, skipping announcement",
    );
    return;
  }

  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        embeds: [
          {
            title: payload.title,
            description: payload.description,
            fields: payload.fields,
          },
        ],
      }),
    });
    if (!response.ok) {
      console.warn(
        "Failed to send Discord announcement",
        response.status,
        await response.text(),
      );
    }
  } catch (error) {
    console.warn("Failed to send Discord announcement", error);
  }
}

function pushField(
  fields: DiscordField[],
  name: string,
  rawValue: unknown,
): void {
  if (typeof rawValue !== "string") return;
  const value = rawValue.trim();
  if (!value) return;
  fields.push({ name, value });
}

export async function announceNewSoftmaxSignup(params: {
  user: User;
  account: Account;
  profile?: Profile;
}): Promise<void> {
  const { user, account, profile } = params;
  const provider = account.provider;
  const providerLabel = provider.slice(0, 1).toUpperCase() + provider.slice(1);
  const displayName =
    user.name?.trim() || user.email?.trim() || user.id || "New user";
  const fields: DiscordField[] = [];

  pushField(fields, "Name", user.name);
  pushField(fields, "Email", user.email);
  pushField(fields, "User ID", user.id);
  pushField(fields, "Provider", providerLabel);

  if (provider === "github") {
    const login =
      typeof profile?.login === "string" ? profile.login.trim() : "";
    const githubUrl =
      typeof profile?.html_url === "string" && profile.html_url.trim()
        ? profile.html_url.trim()
        : login
          ? `https://github.com/${login}`
          : "";
    pushField(fields, "GitHub", githubUrl);
  } else {
    pushField(fields, "Profile", profile?.profile);
    pushField(fields, "Website", profile?.website);
  }

  fields.push({
    name: "Softmax",
    value: getSiteUrl(),
  });

  await sendDiscordAnnouncement({
    title: "New Softmax signup",
    description: `${displayName} signed up on Softmax via ${providerLabel}.`,
    fields,
  });
}
