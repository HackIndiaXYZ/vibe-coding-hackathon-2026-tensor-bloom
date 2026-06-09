// The ◇ COSIGN sign-off seal. Used on the gate and on completed goals.
export function SignatureStamp({
  signed = false,
  login,
  className = "",
}: {
  signed?: boolean;
  login?: string;
  className?: string;
}) {
  return (
    <div
      className={`inline-flex select-none items-center gap-2 border px-3 py-1.5 mono text-xs ${className}`}
      style={{
        borderColor: signed ? "var(--ok)" : "var(--cyan-dim)",
        color: signed ? "var(--ok)" : "var(--cyan)",
        letterSpacing: "0.22em",
      }}
    >
      <span style={{ transform: "rotate(45deg)", display: "inline-block" }}>◇</span>
      <span>{signed ? "COSIGNED" : "COSIGN"}</span>
      {login && <span className="text-[var(--text-dim)]">· @{login}</span>}
    </div>
  );
}
