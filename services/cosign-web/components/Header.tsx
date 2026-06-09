"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export function Header() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null));
  }, []);

  return (
    <header className="border-b border-neutral-200 dark:border-neutral-800">
      <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
        <Link href="/" className="font-semibold">
          Cosign
        </Link>
        <nav className="flex gap-3 text-sm text-neutral-600 dark:text-neutral-400">
          <Link href="/review" className="hover:underline">Review PR</Link>
          <Link href="/resolve" className="hover:underline">Resolve Issue</Link>
        </nav>
        <div className="ml-auto text-sm">
          {user ? (
            <span className="flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={user.avatar_url} alt="" className="h-6 w-6 rounded-full" />
              <span>{user.github_login}</span>
            </span>
          ) : (
            <a
              href={api.loginUrl()}
              className="rounded bg-black px-3 py-1.5 text-white dark:bg-white dark:text-black"
            >
              Sign in with GitHub
            </a>
          )}
        </div>
      </div>
    </header>
  );
}
