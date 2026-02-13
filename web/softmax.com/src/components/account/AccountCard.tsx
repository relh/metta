"use client";

import clsx from "clsx";
import { signOut } from "next-auth/react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "../Button";

type AccountCardProps = {
  user: {
    name: string | null;
    email: string | null;
    institution: string | null;
    profileCompleted: boolean;
  };
};

type StoredValues = {
  name: string;
  email: string;
  institution: string;
  hasAcceptedTos: boolean;
};

export function AccountCard({ user }: AccountCardProps) {
  const router = useRouter();
  const initialValuesRef = useRef<StoredValues>({
    name: user.name ?? "",
    email: user.email ?? "",
    institution: user.institution ?? "",
    hasAcceptedTos: user.profileCompleted ?? false,
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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    const nextValues: StoredValues = {
      name: user.name ?? "",
      email: user.email ?? "",
      institution: user.institution ?? "",
      hasAcceptedTos: user.profileCompleted ?? false,
    };

    const prev = initialValuesRef.current;
    if (
      nextValues.name !== prev.name ||
      nextValues.email !== prev.email ||
      nextValues.institution !== prev.institution ||
      nextValues.hasAcceptedTos !== prev.hasAcceptedTos
    ) {
      initialValuesRef.current = nextValues;
      setName(nextValues.name);
      setEmail(nextValues.email);
      setInstitution(nextValues.institution);
      setHasAcceptedTos(nextValues.hasAcceptedTos);
    }
  }, [user.name, user.email, user.institution, user.profileCompleted]);

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
    hasAcceptedTos !== initialValuesRef.current.hasAcceptedTos;

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
        };
      };

      const updatedValues: StoredValues = {
        name: data.user.name ?? "",
        email: data.user.email ?? "",
        institution: data.user.institution ?? "",
        hasAcceptedTos: data.user.profileCompleted,
      };

      initialValuesRef.current = updatedValues;
      setName(updatedValues.name);
      setEmail(updatedValues.email);
      setInstitution(updatedValues.institution);
      setHasAcceptedTos(updatedValues.hasAcceptedTos);
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
            I have read and agree to the{" "}
            <a
              href="/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-[#1a3875] underline"
            >
              Terms & Privacy Policy
            </a>
            .
          </span>
        </label>

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
              : "Complete all fields and confirm the Terms to finish your profile."}
          </p>
        )}
      </form>
    </div>
  );
}
