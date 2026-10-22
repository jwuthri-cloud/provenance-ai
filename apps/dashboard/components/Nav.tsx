"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS: [string, string][] = [
  ["/", "Overview"],
  ["/files", "Files"],
  ["/sessions", "Sessions"],
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 border-r border-white/10 px-5 py-7">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-semibold text-white">trace</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-300">M4</span>
      </div>
      <div className="text-xs text-slate-500 mb-8">AI authorship</div>
      <nav className="flex flex-col gap-1">
        {ITEMS.map(([href, label]) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`px-3 py-2 rounded-lg text-sm transition-colors ${
                active ? "bg-white/10 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-10 text-[11px] text-slate-600 leading-relaxed">
        Reads the local daemon.<br />Cloud sync + teams is full M4.
      </div>
    </aside>
  );
}
