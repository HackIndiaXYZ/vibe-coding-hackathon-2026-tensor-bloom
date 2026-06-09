export function DiffViewer({ diff }: { diff: string }) {
  if (!diff) return <div className="mono text-xs text-[var(--text-dim)]">no diff</div>;
  const lines = diff.split("\n");
  return (
    <pre className="overflow-x-auto border border-[var(--line)] bg-[var(--ink)] p-3 text-xs leading-5 mono">
      {lines.map((ln, i) => {
        let color = "var(--text-dim)";
        let bg = "transparent";
        if (ln.startsWith("+") && !ln.startsWith("+++")) {
          color = "var(--ok)";
          bg = "rgba(52,211,153,0.07)";
        } else if (ln.startsWith("-") && !ln.startsWith("---")) {
          color = "var(--danger)";
          bg = "rgba(248,113,113,0.07)";
        } else if (ln.startsWith("@@")) {
          color = "var(--cyan)";
        } else if (ln.startsWith("diff ") || ln.startsWith("index ")) {
          color = "var(--text-faint)";
        } else {
          color = "var(--text)";
        }
        return (
          <div key={i} style={{ color, background: bg }} className="px-1">
            {ln || " "}
          </div>
        );
      })}
    </pre>
  );
}
