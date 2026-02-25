"use client";

import { setOutageSimulated } from "@observatory/lib/debug/simulate-outage";
import { FC } from "react";

export const DisableOutageButton: FC = () => {
  return (
    <button
      className="mt-4 cursor-pointer rounded-md bg-red-600 px-4 py-2 text-white hover:bg-red-700"
      onClick={() => {
        setOutageSimulated(false);
        window.location.reload();
      }}
    >
      Disable Simulated API Outage
    </button>
  );
};
