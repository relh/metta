"use client";

import { FC } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const GameDescription: FC<{ description: string }> = ({
  description,
}) => {
  return (
    <details className="group">
      <summary className="text-foreground-muted hover:text-foreground cursor-pointer text-sm font-medium transition-colors select-none">
        About this game
      </summary>
      <div className="border-border mt-3 rounded-lg border p-4">
        <Markdown
          remarkPlugins={[remarkGfm]}
          children={description}
          components={{
            p: ({ children }) => (
              <p className="text-foreground-muted mb-3 text-sm last:mb-0">
                {children}
              </p>
            ),
            strong: ({ children }) => (
              <strong className="text-foreground font-semibold">
                {children}
              </strong>
            ),
            table: ({ children }) => (
              <table className="text-foreground-muted mb-3 w-full text-sm">
                {children}
              </table>
            ),
            thead: ({ children }) => (
              <thead className="border-border border-b">{children}</thead>
            ),
            th: ({ children }) => (
              <th className="text-foreground px-3 py-1.5 text-left text-xs font-semibold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border-border border-t px-3 py-1.5">{children}</td>
            ),
          }}
        />
      </div>
    </details>
  );
};
