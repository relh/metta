"use client";

import clsx from "clsx";
import { signIn, signOut } from "next-auth/react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { DISCORD_INVITE_URL } from "@/lib/constants";
import { CURRENT_TOS_VERSION } from "@/lib/tos";

import { linkClassName } from "../A";
import { Button } from "../Button";

type AccountCardProps = {
  user: {
    name: string | null;
    email: string | null;
    institution: string | null;
    profileCompleted: boolean;
    tosVersion: string | null;
    consentServiceUpdates: boolean;
    consentMarketing: boolean;
  };
  discordUserId?: string | null;
  discordEnabled?: boolean;
};

type StoredValues = {
  name: string;
  email: string;
  institution: string;
  hasAcceptedTos: boolean;
  consentServiceUpdates: boolean;
  consentMarketing: boolean;
};

export function AccountCard({
  user,
  discordUserId,
  discordEnabled,
}: AccountCardProps) {
  const router = useRouter();

  const needsReConsent =
    user.tosVersion !== null && user.tosVersion !== CURRENT_TOS_VERSION;

  const initialValuesRef = useRef<StoredValues>({
    name: user.name ?? "",
    email: user.email ?? "",
    institution: user.institution ?? "",
    hasAcceptedTos: user.tosVersion === CURRENT_TOS_VERSION,
    consentServiceUpdates: user.consentServiceUpdates,
    consentMarketing: user.consentMarketing,
  });
  const successFlashRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [name, setName] = useState(initialValuesRef.current.name);
  const [email, setEmail] = useState(initialValuesRef.current.email);
  const [institution, setInstitution] = useState(
    initialValuesRef.current.institution,
  );
  const [hasAcceptedTos, setHasAcceptedTos] = useState(
    initialValuesRef.current.hasAcceptedTos,
  );
  const [consentServiceUpdates, setConsentServiceUpdates] = useState(
    initialValuesRef.current.consentServiceUpdates,
  );
  const [consentMarketing, setConsentMarketing] = useState(
    initialValuesRef.current.consentMarketing,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    const nextValues: StoredValues = {
      name: user.name ?? "",
      email: user.email ?? "",
      institution: user.institution ?? "",
      hasAcceptedTos: user.tosVersion === CURRENT_TOS_VERSION,
      consentServiceUpdates: user.consentServiceUpdates,
      consentMarketing: user.consentMarketing,
    };

    const prev = initialValuesRef.current;
    if (
      nextValues.name !== prev.name ||
      nextValues.email !== prev.email ||
      nextValues.institution !== prev.institution ||
      nextValues.hasAcceptedTos !== prev.hasAcceptedTos ||
      nextValues.consentServiceUpdates !== prev.consentServiceUpdates ||
      nextValues.consentMarketing !== prev.consentMarketing
    ) {
      initialValuesRef.current = nextValues;
      setName(nextValues.name);
      setEmail(nextValues.email);
      setInstitution(nextValues.institution);
      setHasAcceptedTos(nextValues.hasAcceptedTos);
      setConsentServiceUpdates(nextValues.consentServiceUpdates);
      setConsentMarketing(nextValues.consentMarketing);
    }
  }, [
    user.name,
    user.email,
    user.institution,
    user.tosVersion,
    user.consentServiceUpdates,
    user.consentMarketing,
  ]);

  useEffect(() => {
    return () => {
      if (successFlashRef.current) {
        clearTimeout(successFlashRef.current);
      }
    };
  }, []);

  const profileComplete =
    name.trim().length > 0 &&
    email.trim().length > 0 &&
    institution.trim().length > 0 &&
    hasAcceptedTos;

  const hasChanges =
    name !== initialValuesRef.current.name ||
    email !== initialValuesRef.current.email ||
    institution !== initialValuesRef.current.institution ||
    hasAcceptedTos !== initialValuesRef.current.hasAcceptedTos ||
    consentServiceUpdates !== initialValuesRef.current.consentServiceUpdates ||
    consentMarketing !== initialValuesRef.current.consentMarketing;

  const tosLocked = initialValuesRef.current.hasAcceptedTos;

  const clearErrorAndSuccess = () => {
    if (error) {
      setError(null);
    }
    if (showSuccess) {
      setShowSuccess(false);
      if (successFlashRef.current) {
        clearTimeout(successFlashRef.current);
        successFlashRef.current = null;
      }
    }
  };

  const handleSignOut = () => {
    const target =
      typeof window !== "undefined" && window.top
        ? window.top.location.href
        : undefined;
    void signOut({ callbackUrl: target });
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasChanges) return;

    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch("/api/user", {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({
          name,
          email,
          institution,
          hasAcceptedTos,
          consentServiceUpdates,
          consentMarketing,
        }),
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        const message =
          data?.error ?? "Unable to save your profile. Please try again.";
        setError(message);
        return;
      }

      const data = (await response.json()) as {
        user: {
          name: string | null;
          email: string | null;
          institution: string | null;
          profileCompleted: boolean;
          tosVersion: string | null;
          consentServiceUpdates: boolean;
          consentMarketing: boolean;
        };
      };

      const updatedValues: StoredValues = {
        name: data.user.name ?? "",
        email: data.user.email ?? "",
        institution: data.user.institution ?? "",
        hasAcceptedTos: data.user.tosVersion === CURRENT_TOS_VERSION,
        consentServiceUpdates: data.user.consentServiceUpdates,
        consentMarketing: data.user.consentMarketing,
      };

      initialValuesRef.current = updatedValues;
      setName(updatedValues.name);
      setEmail(updatedValues.email);
      setInstitution(updatedValues.institution);
      setHasAcceptedTos(updatedValues.hasAcceptedTos);
      setConsentServiceUpdates(updatedValues.consentServiceUpdates);
      setConsentMarketing(updatedValues.consentMarketing);
      setError(null);
      if (data.user.profileCompleted) {
        setShowSuccess(true);
        if (successFlashRef.current) {
          clearTimeout(successFlashRef.current);
        }
        successFlashRef.current = setTimeout(() => {
          setShowSuccess(false);
          successFlashRef.current = null;
        }, 2000);
      } else {
        setShowSuccess(false);
      }
      router.refresh();
    } catch (submitError) {
      console.error("Error saving profile", submitError);
      setError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-8">
      {needsReConsent && (
        <div className="mb-6 rounded-lg border border-[#c9a825] bg-[#fef9e7] px-3 py-2 text-sm text-[#7a6c14]">
          We&apos;ve updated our Terms of Service. Please review and accept to
          keep your profile current.
        </div>
      )}

      {error ? (
        <div className="mb-6 rounded-lg border border-[#d9534f] bg-[#f9eaea] px-3 py-2 text-sm text-[#a94442]">
          {error}
        </div>
      ) : null}

      <form className="space-y-5 text-sm text-[#333]" onSubmit={handleSubmit}>
        <fieldset className="space-y-1">
          <label
            className="block text-left text-xs font-semibold tracking-wide text-[#0e2758] uppercase"
            htmlFor="account-name"
          >
            name
          </label>
          <input
            id="account-name"
            type="text"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              clearErrorAndSuccess();
            }}
            className="w-full rounded-lg border border-[#d8d2bf] bg-white px-3 py-2 text-sm text-[#0e2758] focus:border-[#0e2758] focus:ring-2 focus:ring-[#0e2758]/20 focus:outline-none"
            placeholder="Ada Lovelace"
            autoComplete="name"
            required
          />
        </fieldset>

        <fieldset className="space-y-1">
          <label
            className="block text-left text-xs font-semibold tracking-wide text-[#0e2758] uppercase"
            htmlFor="account-email"
          >
            email
          </label>
          <input
            id="account-email"
            type="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              clearErrorAndSuccess();
            }}
            className="w-full rounded-lg border border-[#d8d2bf] bg-white px-3 py-2 text-sm text-[#0e2758] focus:border-[#0e2758] focus:ring-2 focus:ring-[#0e2758]/20 focus:outline-none"
            placeholder="ada@example.com"
            autoComplete="email"
            required
          />
        </fieldset>

        <fieldset className="space-y-1">
          <label
            className="block text-left text-xs font-semibold tracking-wide text-[#0e2758] uppercase"
            htmlFor="account-institution"
          >
            institution
          </label>
          <input
            id="account-institution"
            type="text"
            value={institution}
            onChange={(event) => {
              setInstitution(event.target.value);
              clearErrorAndSuccess();
            }}
            className="w-full rounded-lg border border-[#d8d2bf] bg-white px-3 py-2 text-sm text-[#0e2758] focus:border-[#0e2758] focus:ring-2 focus:ring-[#0e2758]/20 focus:outline-none"
            placeholder="Your Research Group"
            autoComplete="organization"
            required
          />
        </fieldset>

        {/* Required consent */}
        <div className="space-y-2 border-t border-[#d8d2bf] pt-4">
          <p className="text-xs font-semibold tracking-wide text-[#0e2758] uppercase">
            required
          </p>
          <label className="flex items-start gap-3 text-left text-sm leading-6 text-[#0e2758]">
            <input
              type="checkbox"
              checked={hasAcceptedTos || tosLocked}
              onChange={(event) => {
                if (tosLocked) return;
                setHasAcceptedTos(event.target.checked);
                clearErrorAndSuccess();
              }}
              disabled={tosLocked}
              className="mt-1 h-4 w-4 rounded border border-[#d8d2bf] text-[#0e2758] focus:ring-[#0e2758] disabled:cursor-not-allowed disabled:border-[#b7b2a3] disabled:text-[#8590aa]"
            />
            <span className={tosLocked ? "text-[#4a5f8c]" : undefined}>
              I agree to the{" "}
              <a
                href="/terms"
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-[#1a3875] underline"
              >
                Terms of Service
              </a>
              {" and "}
              <a
                href="/privacy"
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-[#1a3875] underline"
              >
                Privacy Policy
              </a>
              .
            </span>
          </label>
        </div>

        {/* Optional communication preferences */}
        <div className="space-y-2 border-t border-[#d8d2bf] pt-4">
          <p className="text-xs font-semibold tracking-wide text-[#0e2758] uppercase">
            stay in touch (optional)
          </p>
          <label className="flex items-start gap-3 text-left text-sm leading-6 text-[#0e2758]">
            <input
              type="checkbox"
              checked={consentServiceUpdates}
              onChange={(event) => {
                setConsentServiceUpdates(event.target.checked);
                clearErrorAndSuccess();
              }}
              className="mt-1 h-4 w-4 rounded border border-[#d8d2bf] text-[#0e2758] focus:ring-[#0e2758]"
            />
            <span>
              Send me service updates (competition results, account activity)
            </span>
          </label>
          <label className="flex items-start gap-3 text-left text-sm leading-6 text-[#0e2758]">
            <input
              type="checkbox"
              checked={consentMarketing}
              onChange={(event) => {
                setConsentMarketing(event.target.checked);
                clearErrorAndSuccess();
              }}
              className="mt-1 h-4 w-4 rounded border border-[#d8d2bf] text-[#0e2758] focus:ring-[#0e2758]"
            />
            <span>Send me news about new offerings from Softmax</span>
          </label>
        </div>

        {(discordEnabled || discordUserId) && (
          <div className="space-y-2 border-t border-[#d8d2bf] pt-4">
            <p className="text-xs font-semibold tracking-wide text-[#0e2758] uppercase">
              linked accounts
            </p>
            {discordUserId ? (
              <>
                <a
                  href={`https://discord.com/users/${discordUserId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`inline-flex items-center gap-2 text-sm ${linkClassName}`}
                  title="View Discord profile"
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 -28.5 256 256"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <path
                      d="M216.856 16.597A208.502 208.502 0 0 0 164.042 0c-2.275 4.113-4.933 9.645-6.766 14.046-19.692-2.961-39.203-2.961-58.533 0-1.832-4.4-4.55-9.933-6.846-14.046a207.809 207.809 0 0 0-52.855 16.638C5.618 67.147-3.443 116.4 1.087 164.956c22.169 16.555 43.653 26.612 64.775 33.193a161.094 161.094 0 0 0 13.882-22.584 136.426 136.426 0 0 1-21.846-10.632 108.636 108.636 0 0 0 5.356-4.237c42.122 19.702 87.89 19.702 129.51 0a131.66 131.66 0 0 0 5.355 4.237 136.07 136.07 0 0 1-21.886 10.653c4.006 8.02 8.638 15.67 13.862 22.564 21.142-6.581 42.646-16.637 64.815-33.213 5.316-56.288-9.08-105.09-38.056-148.36ZM85.474 135.095c-12.645 0-23.015-11.805-23.015-26.18s10.149-26.2 23.015-26.2c12.867 0 23.236 11.804 23.015 26.2.02 14.375-10.148 26.18-23.015 26.18Zm85.051 0c-12.645 0-23.014-11.805-23.014-26.18s10.148-26.2 23.014-26.2c12.867 0 23.236 11.804 23.015 26.2 0 14.375-10.148 26.18-23.015 26.18Z"
                      fill="currentColor"
                    />
                  </svg>
                  Discord
                </a>
                <p className="mt-2 text-sm text-[#4a5f8c]">
                  To receive notifications,{" "}
                  <a
                    href={DISCORD_INVITE_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={linkClassName}
                  >
                    join our Discord server
                  </a>
                  .
                </p>
              </>
            ) : (
              <Button
                type="button"
                onClick={() =>
                  void signIn("discord", { callbackUrl: "/account" })
                }
              >
                Link Discord
              </Button>
            )}
          </div>
        )}

        <div className="flex flex-wrap justify-between gap-3 pt-2">
          <Button
            theme="primary"
            type="submit"
            disabled={submitting || !hasChanges}
          >
            {submitting ? "Updating..." : "Update Profile"}
          </Button>
          <Button type="button" onClick={handleSignOut}>
            Log Out
          </Button>
        </div>

        {(!profileComplete || (profileComplete && showSuccess)) && (
          <p
            className={clsx(
              "rounded-md px-2 py-2 text-sm transition-colors duration-300",
              profileComplete ? "text-[#2e7d32]" : "text-[#4a5f8c]",
              showSuccess && profileComplete
                ? "bg-[#e9f7eb]"
                : "bg-transparent",
            )}
          >
            {profileComplete
              ? "Your profile is complete."
              : "Complete all fields and accept the Terms to finish your profile."}
          </p>
        )}
      </form>
    </div>
  );
}
