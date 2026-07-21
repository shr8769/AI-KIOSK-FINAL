"use client";
import * as React from "react"
import { useEffect, useState } from "react";
 
import ReactMarkdown from 'react-markdown';

export interface TypewriterProps {
  text: string | string[];
  speed?: number;
  cursor?: string;
  loop?: boolean;
  deleteSpeed?: number;
  delay?: number;
  className?: string;
  useMarkdown?: boolean;
}
 
export function Typewriter({
  text,
  speed = 100,
  cursor = "|",
  loop = false,
  deleteSpeed = 50,
  delay = 1500,
  className,
  useMarkdown = true,
}: TypewriterProps) {
  const [displayText, setDisplayText] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [textArrayIndex, setTextArrayIndex] = useState(0);
 
  // Validate and process input text
  const textArray = Array.isArray(text) ? text : [text];
  const currentText = textArray[textArrayIndex] || "";
 
  useEffect(() => {
    if (!currentText) return;
 
    const timeout = setTimeout(
      () => {
        if (!isDeleting) {
          if (currentIndex < currentText.length) {
            setDisplayText((prev) => prev + currentText[currentIndex]);
            setCurrentIndex((prev) => prev + 1);
          } else if (loop) {
            setTimeout(() => setIsDeleting(true), delay);
          }
        } else {
          if (displayText.length > 0) {
            setDisplayText((prev) => prev.slice(0, -1));
          } else {
            setIsDeleting(false);
            setCurrentIndex(0);
            setTextArrayIndex((prev) => (prev + 1) % textArray.length);
          }
        }
      },
      isDeleting ? deleteSpeed : speed,
    );
 
    return () => clearTimeout(timeout);
  }, [
    currentIndex,
    isDeleting,
    currentText,
    loop,
    speed,
    deleteSpeed,
    delay,
    displayText,
    text,
  ]);
 
  return (
    <span className={className}>
      {useMarkdown ? (
        <ReactMarkdown
          components={{
            p: ({node, ...props}) => <span {...props} />,
            a: ({node, ...props}) => <a className="text-blue-400 underline" {...props} />,
            strong: ({node, ...props}) => <strong className="font-bold text-white" {...props} />,
            em: ({node, ...props}) => <em className="italic text-zinc-300" {...props} />,
            ul: ({node, ...props}) => <ul className="list-disc list-inside text-left my-2" {...props} />,
            ol: ({node, ...props}) => <ol className="list-decimal list-inside text-left my-2" {...props} />,
            li: ({node, ...props}) => <li className="my-1" {...props} />
          }}
        >
          {displayText + (currentIndex < currentText.length ? cursor : "")}
        </ReactMarkdown>
      ) : (
        <>
          {displayText}
          <span className="animate-pulse">{cursor}</span>
        </>
      )}
    </span>
  );
}
