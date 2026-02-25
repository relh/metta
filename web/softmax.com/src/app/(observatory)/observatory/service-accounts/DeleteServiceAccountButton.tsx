"use client";
import { useRouter } from "next/navigation";
import { FC, use, useState } from "react";
import { toast } from "react-toastify";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";
import { Spinner } from "@observatory/components/Spinner";

export const DeleteServiceAccountButton: FC<{ id: string; name: string }> = ({
  id,
  name,
}) => {
  const { repo } = use(AppContext);
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await repo.deleteServiceAccount(id);
      router.refresh();
    } catch (err: unknown) {
      toast.error("Failed to delete service account.", {
        autoClose: 3000,
        hideProgressBar: true,
        toastId: "delete-service-account-error",
      });
      setDeleting(false);
      setConfirming(false);
    }
  };

  if (!confirming) {
    return (
      <Button onClick={() => setConfirming(true)} theme="tertiary">
        <div className="flex size-full items-center justify-center">
          <TrashIcon />
        </div>
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <Button onClick={handleDelete} theme="tertiary" disabled={deleting}>
        <div className="text-red-600">
          {deleting ? <Spinner size="sm" /> : "Delete"}
        </div>
      </Button>

      <Button
        onClick={() => setConfirming(false)}
        theme="tertiary"
        disabled={deleting}
      >
        Cancel
      </Button>
    </div>
  );
};

function TrashIcon() {
  return (
    <svg
      className="h-4 w-4"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  );
}
