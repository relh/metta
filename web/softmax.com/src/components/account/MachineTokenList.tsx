import { InlineCode } from "../InlineCode";
import { P } from "../P";
import { Table, TBody, TD, TH, THead, TR } from "../Table";

type MachineToken = {
  id: string;
  name: string;
  tokenHash: string;
  createdAt: Date;
  lastUsedAt: Date | null;
};

function obfuscate(hash: string) {
  if (hash.length <= 10) return hash;
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`;
}

function formatDate(value: Date | null) {
  if (!value) return "never";
  return value.toLocaleString();
}

export function MachineTokenList({ tokens }: { tokens: MachineToken[] }) {
  return (
    <div className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
      <div className="mb-4 space-y-2">
        <P>
          Run <InlineCode>cogames login</InlineCode> to create a new token.
        </P>
      </div>

      {tokens.length === 0 ? (
        <P>No active CLI sessions yet.</P>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <THead>
              <TH>Token</TH>
              <TH>Created</TH>
              <TH>Last used</TH>
            </THead>
            <TBody>
              {tokens.map((token) => (
                <TR key={token.id}>
                  <TD>
                    <InlineCode>{obfuscate(token.tokenHash)}</InlineCode>
                  </TD>
                  <TD>{formatDate(token.createdAt)}</TD>
                  <TD>{formatDate(token.lastUsedAt)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )}
    </div>
  );
}
