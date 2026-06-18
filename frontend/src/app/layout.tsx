import React from 'react';
import { Cinzel, Outfit, JetBrains_Mono } from 'next/font/google';
import './globals.css';

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
  title: 'VidyaSahayak AI Kiosk',
  description: 'AI Avatar Kiosk for PES University',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${cinzel.variable} ${outfit.variable} ${jbMono.variable} font-sans min-h-screen bg-background text-foreground antialiased selection:bg-white selection:text-black`}>
        {children}
      </body>
    </html>
  );
}
