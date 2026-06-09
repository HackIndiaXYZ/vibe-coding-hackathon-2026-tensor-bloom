"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

const NAV = [
  { href: "/review", label: "review" },
  { href: "/resolve", label: "resolve" },
  { href: "/settings", label: "settings" },
];

export function Header() {
  const [user, setUser] = useState<User | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null));
  }, []);

  return (
    <header className="sticky top-0 z-20 border-b border-[var(--line)] bg-[color:var(--ink)]/85 backdrop-blur-sm">
      <div className="mx-auto flex max-w-5xl items-center gap-6 px-5 py-3">
        <Link href="/" className="mono flex items-center gap-2 text-sm font-600 tracking-[0.18em] text-[var(--text)]">
          <span className="text-[var(--cyan)]" style={{ transform: "rotate(45deg)", display: "inline-block" }}>◇</span>
          COSIGN
        </Link>
        <nav className="flex gap-4">
          {NAV.map((n) => {
            const on = pathname === n.href;
            return (
              <Link
                key={n.href}
                href={n.href}
                className="label transition-colors hover:text-[var(--cyan)]"
                style={on ? { color: "var(--cyan)" } : undefined}
              >
                {on ? `[ ${n.label} ]` : n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto">
          {user ? (
            <span className="mono flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <span className="text-[var(--cyan)]" style={{ transform: "rotate(45deg)", display: "inline-block" }}>◇</span>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={user.avatar_url} alt="" className="h-5 w-5 rounded-none border border-[var(--line)]" />
              {user.github_login}
            </span>
          ) : (
            <a href={api.loginUrl()} className="btn btn-primary">
              sign in with github
            </a>
          )}
        </div>
      </div>
    </header>
  );
}
