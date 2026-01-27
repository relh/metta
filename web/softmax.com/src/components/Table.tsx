import { FC, PropsWithChildren } from "react";

export const Table = ({
  children,
  fixed,
}: {
  children: React.ReactNode;
  fixed?: boolean;
}) => {
  return (
    <table
      className={`w-full text-sm text-[#333] ${fixed ? "table-fixed" : ""}`}
    >
      {children}
    </table>
  );
};

export const THead: FC<PropsWithChildren> = ({ children }) => {
  return (
    <thead>
      <tr className="text-xs tracking-wide text-[#4a5f8c] uppercase">
        {children}
      </tr>
    </thead>
  );
};

export const TBody: FC<PropsWithChildren> = ({ children }) => {
  return <tbody>{children}</tbody>;
};

export const TH: FC<PropsWithChildren<{ className?: string }>> = ({
  children,
  className,
}) => {
  return (
    <th className={`pb-2 text-left font-semibold ${className ?? ""}`}>
      {children}
    </th>
  );
};

export const TR: FC<PropsWithChildren<{ className?: string }>> = ({
  children,
  className,
}) => {
  return (
    <tr
      className={`border-b border-[#e6dcc2] last:border-b-0 ${className ?? ""}`}
    >
      {children}
    </tr>
  );
};

export const TD: FC<PropsWithChildren<{ className?: string }>> = ({
  children,
  className,
}) => {
  return (
    <td className={`py-2 pr-4 text-[#4a5f8c] ${className ?? ""}`}>
      {children}
    </td>
  );
};
