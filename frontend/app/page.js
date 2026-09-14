"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("token");
    router.replace(token ? "/chat" : "/login");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center text-gray-400">
      Loading...
    </div>
  );
}
