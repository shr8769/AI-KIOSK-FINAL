import React from 'react';
import { Cinzel, Outfit, JetBrains_Mono } from 'next/font/google';
import './admin.css';

const cinzel = Cinzel({
  subsets: ['latin'],
  variable: '--font-cinzel',
  display: 'swap',
});

const outfit = Outfit({
  subsets: ['latin'],
  variable: '--font-outfit',
  display: 'swap',
});

const jbMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata = {
  title: 'Admin Dashboard — VidyaSahayak',
  description: 'Knowledge management and sync monitoring dashboard for the AI Kiosk',
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className={`${cinzel.variable} ${outfit.variable} ${jbMono.variable} font-sans min-h-screen antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
