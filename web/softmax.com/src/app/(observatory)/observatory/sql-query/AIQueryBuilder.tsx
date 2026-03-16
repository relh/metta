import { FC, use, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";
import { getDisplayMessage } from "@observatory/lib/error-classification";

export const AIQueryBuilder: FC<{
  onQueryGenerated: (query: string) => void;
}> = ({ onQueryGenerated }) => {
  const { repo } = use(AppContext);
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateQuery = async () => {
    const trimmedDescription = description.trim();
    if (!trimmedDescription) {
      setError("Please describe your query");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const { query } = await repo.generateAIQuery(trimmedDescription);
      onQueryGenerated(query);
      setDescription("");
    } catch (err) {
      setError(
        err instanceof Error
          ? getDisplayMessage(err)
          : "Failed to generate query",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      generateQuery();
    }
  };

  return (
    <div className="mb-4 rounded-md border border-blue-200 bg-sky-50 p-4 dark:border-blue-800 dark:bg-sky-950">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="m-0 text-sm font-semibold tracking-wide text-blue-800 uppercase dark:text-blue-300">
          Describe your query
        </h3>
      </div>

      <textarea
        className="border-border-strong bg-surface text-foreground mb-3 min-h-[60px] w-full resize-y rounded border p-2.5 text-sm leading-normal focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 focus:outline-none"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="e.g., Show me the top 10 training runs by average reward"
        disabled={loading}
      />
      <div>
        <Button
          size="sm"
          theme="primary"
          onClick={generateQuery}
          disabled={loading || !description.trim()}
        >
          {loading ? "Generating..." : "Generate Query"}
        </Button>
      </div>

      {error && <div className="mt-2 text-xs text-red-600">{error}</div>}
    </div>
  );
};
