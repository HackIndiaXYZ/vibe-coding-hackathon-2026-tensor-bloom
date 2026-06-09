export function DiffViewer({ diff }: { diff: string }) {
  if (!diff) return <div className="text-xs text-neutral-500">No diff.</div>;
  const lines = diff.split("\n");
  return (
    <pre className="overflow-x-auto rounded bg-neutral-950 p-3 text-xs leading-5 text-neutral-200">
      {lines.map((ln, i) => {
        let cls = "";
        if (ln.startsWith("+") && !ln.startsWith("+++")) cls = "bg-emerald-950/60 text-emerald-300";
        else if (ln.startsWith("-") && !ln.startsWith("---")) cls = "bg-red-950/60 text-red-300";
        else if (ln.startsWith("@@")) cls = "text-cyan-400";
        else if (ln.startsWith("diff ") || ln.startsWith("index ")) cls = "text-neutral-500";
        return (
          <div key={i} className={cls}>
            {ln || " "}
          </div>
        );
      })}
    </pre>
  );
}
