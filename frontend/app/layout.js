import "./globals.css";

export const metadata = {
  title: "NGINX Assistant",
  description: "Chat with your infrastructure monitoring agent",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="relative bg-white antialiased">
        <main>{children}</main>
      </body>
    </html>
  );
}
