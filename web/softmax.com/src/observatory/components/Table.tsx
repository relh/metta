"use client";
import clsx from "clsx";
import { createContext, FC, PropsWithChildren, use } from "react";

type TableTheme = "large" | "inner" | "light";

const TableContext = createContext<{ theme: TableTheme }>({ theme: "large" });

export const Table: FC<PropsWithChildren<{ theme?: TableTheme }>> & {
  Header: FC<PropsWithChildren>;
  Body: FC<PropsWithChildren>;
} = ({ children, theme = "large" }) => {
  return (
    <TableContext value={{ theme }}>
      <table
        className={clsx(
          "w-full border-collapse",
          theme === "large" && "text-sm",
          theme === "inner" && "text-xs",
          theme === "light" && "text-sm",
        )}
      >
        {children}
      </table>
    </TableContext>
  );
};

export const TableHeader: FC<PropsWithChildren> = ({ children }) => {
  return (
    <thead className="bg-surface-alt">
      <tr>{children}</tr>
    </thead>
  );
};

export const TableBody: FC<PropsWithChildren> = ({ children }) => {
  return <tbody>{children}</tbody>;
};

export const TH: FC<React.ThHTMLAttributes<HTMLTableCellElement>> = ({
  className,
  ...props
}) => {
  const { theme } = use(TableContext);

  return (
    <th
      className={clsx(
        "text-foreground-muted text-left align-top text-xs font-bold tracking-[0.04em] uppercase",
        theme === "large" && "border-border border-b px-3 py-2",
        theme === "inner" &&
          "border-border text-foreground-muted bg-surface-alt border p-1.5",
        theme === "light" && "p-2",
        className,
      )}
      {...props}
    />
  );
};

export const TR: FC<React.HTMLAttributes<HTMLTableRowElement>> = ({
  ...props
}) => {
  return <tr {...props} />;
};

export const TD: FC<
  PropsWithChildren<React.TdHTMLAttributes<HTMLTableCellElement>>
> = ({ children, className, ...props }) => {
  const { theme } = use(TableContext);
  return (
    <td
      className={clsx(
        // TODO - use tailwind-merge or tailwind-variants?
        "align-top",
        theme === "large" && "border-border-subtle border-b px-3 py-2",
        theme === "inner" && "border-border border p-1.5",
        theme === "light" && "p-2",
        className,
      )}
      {...props}
    >
      {children}
    </td>
  );
};

Table.Header = TableHeader;
Table.Body = TableBody;
