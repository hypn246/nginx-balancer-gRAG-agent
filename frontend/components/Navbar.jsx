"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

export const NAV_LINKS = [
  { href: "/chat", label: "Chatbot" },
  { href: "/docs", label: "How to use?" },
  { href: "/example", label: "Examples" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const isActive = (href) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className="fixed p-2 inset-x-0 top-0 z-[60] border-b border-gray-100 bg-white">
      <nav className="flex h-16 items-center justify-between p-2 sm:px-4 lg:px-4">
        <Link href="/" className="text-xl font-bold text-black" onClick={() => setMenuOpen(false)}>
          gRAG
        </Link>

        <div id="link" className="items-center gap-2">
          {NAV_LINKS.map((link) => {
            const active = isActive(link.href);
            return (
              <Link key={link.href} href={link.href} className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${active ? "bg-gray-100 text-black" : "text-gray-600 hover:bg-gray-50 hover:text-black"}`}>
                {link.label}
              </Link>
            );
          })}
        </div>

        <button type="button" onClick={() => setMenuOpen((open) => !open)} aria-label={menuOpen ? "Close menu" : "Open menu"} aria-expanded={menuOpen} className="rounded-lg p-2 text-gray-700 hover:bg-gray-100 md:hidden">
          {menuOpen ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="h-6 w-6">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="h-6 w-6">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </nav>

      {menuOpen && (
        <div className="border-t border-gray-100 bg-white py-3 md:hidden">
          <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4">
            {NAV_LINKS.map((link) => {
              const active = isActive(link.href);

              return (
                <Link key={link.href} href={link.href} onClick={() => setMenuOpen(false)} className={`rounded-lg px-4 py-3 text-sm font-medium transition-colors ${active ? "bg-gray-100 text-black" : "text-gray-600 hover:bg-gray-50 hover:text-black"}`}>
                  {link.label}
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </header>
  );
}
