"use client";

import { signIn } from "next-auth/react";

import { Button } from "../Button";

const GITHUB_PROVIDER_ID = "github";

export function AccountSignInPrompt() {
  const redirectTarget =
    typeof window !== "undefined" && window.top
      ? window.top.location.href
      : "/alignmentleague";

  const handleGithubSignIn = () => {
    void signIn(GITHUB_PROVIDER_ID, { callbackUrl: redirectTarget });
  };

  return (
    <div className="rounded-2xl border border-dashed border-[#d8d2bf] bg-[#fffef8] p-8 text-center text-sm text-[#333] shadow-md">
      <p className="mb-6 text-[#4a5f8c]">
        Connect your GitHub account to join the Alignment League, submit your AI
        agents, and view results.
      </p>
      <Button type="button" onClick={handleGithubSignIn} theme="primary">
        Sign in with GitHub
      </Button>
    </div>
  );
}
