"use client";
import { use, useEffect, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import { Spinner } from "@observatory/components/Spinner";
import {
  SQLQueryResponse,
  TableInfo,
  TableSchema,
} from "@observatory/lib/repo";

import { AIQueryBuilder } from "./AIQueryBuilder";
import { QueryResultsTable } from "./QueryResultsTable";
import { QueryHistoryItem, TablesSidebar } from "./TablesSidebar";

type QueryState =
  | { type: "idle" }
  | { type: "loading" }
  | { type: "success"; data: SQLQueryResponse }
  | { type: "error"; error: string };

const HISTORY_KEY = "sql_query_history";
const MAX_HISTORY_ITEMS = 50;

export default function SQLQueryPage() {
  const { repo } = use(AppContext);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableSchema, setTableSchema] = useState<TableSchema | null>(null);
  const [query, setQuery] = useState("");
  const [queryState, setQueryState] = useState<QueryState>({ type: "idle" });
  const [tablesLoading, setTablesLoading] = useState(true);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([]);

  useEffect(() => {
    loadTables();
    loadQueryHistory();
  }, [repo]);

  useEffect(() => {
    if (selectedTable) {
      loadTableSchema(selectedTable);
    } else {
      setTableSchema(null);
    }
  }, [selectedTable, repo]);

  async function loadTables() {
    try {
      setTablesLoading(true);
      const tableList = await repo.listTables();
      setTables(tableList);
    } catch (error) {
      console.error("Failed to load tables:", error);
    } finally {
      setTablesLoading(false);
    }
  }

  async function loadTableSchema(tableName: string) {
    try {
      setSchemaLoading(true);
      const schema = await repo.getTableSchema(tableName);
      setTableSchema(schema);
    } catch (error) {
      console.error("Failed to load table schema:", error);
    } finally {
      setSchemaLoading(false);
    }
  }

  function loadQueryHistory() {
    try {
      const stored = localStorage.getItem(HISTORY_KEY);
      if (stored) {
        const history = JSON.parse(stored) as QueryHistoryItem[];
        setQueryHistory(history);
      }
    } catch (error) {
      console.error("Failed to load query history:", error);
    }
  }

  function saveQueryToHistory(
    queryText: string,
    result: SQLQueryResponse | null,
    error: boolean = false,
  ) {
    const newItem: QueryHistoryItem = {
      query: queryText,
      timestamp: Date.now(),
      rowCount: result?.row_count,
      error,
    };

    const updatedHistory = [
      newItem,
      ...queryHistory.filter((item) => item.query !== queryText),
    ].slice(0, MAX_HISTORY_ITEMS);

    setQueryHistory(updatedHistory);
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updatedHistory));
    } catch (error) {
      console.error("Failed to save query history:", error);
    }
  }

  function clearHistory() {
    setQueryHistory([]);
    try {
      localStorage.removeItem(HISTORY_KEY);
    } catch (error) {
      console.error("Failed to clear query history:", error);
    }
  }

  async function executeQuery() {
    if (!query.trim()) return;

    try {
      setQueryState({ type: "loading" });
      const result = await repo.executeQuery({ query });
      setQueryState({ type: "success", data: result });
      saveQueryToHistory(query, result, false);
    } catch (error) {
      setQueryState({
        type: "error",
        error:
          error instanceof Error ? error.message : "Query execution failed",
      });
      saveQueryToHistory(query, null, true);
    }
  }

  function handleTableClick(tableName: string) {
    setSelectedTable(tableName);
    setQuery(`SELECT * FROM ${tableName} LIMIT 1000`);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      executeQuery();
    }
  }

  return (
    <SoftmaxGuard>
      <div className="flex gap-4 p-4">
        <TablesSidebar
          tables={tables}
          tablesLoading={tablesLoading}
          selectedTable={selectedTable}
          onTableClick={handleTableClick}
          queryHistory={queryHistory}
          onHistoryItemClick={setQuery}
          onClearHistory={clearHistory}
        />

        {/* Query Area */}
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {/* Query Input Section */}
          <div className="border-border bg-surface rounded-lg border p-4">
            <h3 className="text-foreground-subtle mt-0 mb-3 text-sm font-semibold tracking-wide uppercase">
              SQL Query
            </h3>

            {/* Schema Info */}
            {tableSchema && !schemaLoading && (
              <div className="mb-3 rounded border border-blue-200 bg-blue-50 p-3 dark:border-blue-800 dark:bg-blue-950">
                <h4 className="mt-0 mb-2 text-xs font-semibold text-blue-800 dark:text-blue-300">
                  Schema for {tableSchema.table_name}
                </h4>
                <div className="text-xs leading-relaxed">
                  {tableSchema.columns.map((col) => (
                    <div key={col.name} className="mb-0.5 font-mono">
                      <strong>{col.name}</strong>
                      <span className="text-foreground-muted">
                        {" "}
                        ({col.type}
                        {col.nullable ? ", nullable" : ""})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <AIQueryBuilder onQueryGenerated={setQuery} />

            {/* Query Input */}
            <div className="relative">
              <textarea
                className="border-border bg-surface-alt text-foreground focus:bg-surface box-border min-h-[120px] w-full resize-y rounded border p-2.5 pr-36 pb-12 font-mono text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 focus:outline-none"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Enter your SQL query here..."
                spellCheck={false}
              />
              <div className="absolute right-2.5 bottom-2.5">
                <Button
                  theme="primary"
                  size="md"
                  onClick={executeQuery}
                  disabled={!query.trim() || queryState.type === "loading"}
                >
                  {queryState.type === "loading" ? (
                    "Executing..."
                  ) : (
                    <>
                      Execute{" "}
                      <span className="text-xs opacity-80">⌘+Enter</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>

          {/* Results Section */}
          <div className="border-border bg-surface min-w-0 overflow-hidden rounded-lg border p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-foreground-subtle my-0 text-sm font-semibold tracking-wide uppercase">
                Results
              </h3>
              {queryState.type === "success" && (
                <span className="text-foreground-muted text-xs">
                  {queryState.data.row_count} rows returned
                </span>
              )}
            </div>

            {queryState.type === "error" && (
              <div className="mb-4 rounded border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
                <strong>Error:</strong> {queryState.error}
              </div>
            )}

            {queryState.type === "loading" && <Spinner />}

            {queryState.type === "success" &&
              queryState.data.row_count === 0 && (
                <div className="text-foreground-muted py-10 text-center">
                  No results returned
                </div>
              )}

            {queryState.type === "success" && queryState.data.row_count > 0 && (
              <QueryResultsTable data={queryState.data} />
            )}

            {queryState.type === "idle" && (
              <div className="text-foreground-muted py-10 text-center">
                Select a table or enter a query to see results
              </div>
            )}
          </div>
        </div>
      </div>
    </SoftmaxGuard>
  );
}
