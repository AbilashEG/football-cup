import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "Football Cup — AWS AgentCore",
  description:
    "5v5 autonomous football with Strands Agents on Amazon Bedrock AgentCore",
  icons: { icon: "/favicon.ico" },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full">
      <head>
        <link
          rel="preconnect"
          href="https://fonts.googleapis.com"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="h-full flex flex-col overflow-hidden">
        {children}
      </body>
    </html>
  )
}
