"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils/cn";

/**
 * A read-only code panel with optional JSON syntax highlighting.
 *
 * The highlighter is thirty lines of regex rather than Shiki. Shiki ships a
 * WASM grammar engine and a theme bundle — a few hundred kilobytes to colour a
 * webhook payload on a page that only exists in development. JSON has five
 * token classes and no ambiguity worth a real parser, so it gets tokenised
 * here and rendered as spans.
 *
 * Spans, specifically, and never `dangerouslySetInnerHTML`: the payloads shown
 * here are event data, and event data is exactly the kind of thing that should
 * never be able to reach the DOM as markup.
 */

type TokenKind = "key" | "string" | "number" | "keyword" | "punctuation";

interface Token {
  text: string;
  kind: TokenKind;
}

const TOKEN_PATTERN =
  /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"\s*:?)|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)/g;

const TOKEN_CLASS: Record<TokenKind, string> = {
  key: "text-ink-blue",
  string: "text-success",
  number: "text-brand",
  keyword: "text-danger",
  punctuation: "text-ink-faint",
};

function tokenizeJson(source: string): Token[] {
  const tokens: Token[] = [];
  let cursor = 0;

  for (const match of source.matchAll(TOKEN_PATTERN)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      tokens.push({ text: source.slice(cursor, index), kind: "punctuation" });
    }

    const [text, quoted, numeric] = match;
    if (quoted !== undefined) {
      // A quoted run followed by a colon is a key; otherwise it is a value.
      tokens.push({ text, kind: text.trimEnd().endsWith(":") ? "key" : "string" });
    } else if (numeric !== undefined) {
      tokens.push({ text, kind: "number" });
    } else {
      tokens.push({ text, kind: "keyword" });
    }
    cursor = index + text.length;
  }

  if (cursor < source.length) {
    tokens.push({ text: source.slice(cursor), kind: "punctuation" });
  }
  return tokens;
}

interface CodeBlockProps {
  /** Pre-formatted source, or a value that will be pretty-printed as JSON. */
  value: string | unknown;
  language?: "json" | "text";
  /** Shows a copy button in the top-right corner. */
  copyable?: boolean;
  className?: string;
}

export function CodeBlock({ value, language = "json", copyable = true, className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const source = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const tokens = language === "json" ? tokenizeJson(source) : [{ text: source, kind: "punctuation" as const }];

  async function copy() {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      // Long enough to read the tick, short enough not to look stuck.
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied (insecure context, permissions policy).
      // Failing silently is right here: the code is already on screen and
      // selectable, so there is nothing the reader has lost.
    }
  }

  return (
    <div className={cn("group/code relative", className)}>
      {copyable && (
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? "Copied" : "Copy to clipboard"}
          className="absolute top-2 right-2 rounded-md border border-hairline bg-elevated p-1.5 text-ink-faint opacity-0 transition-opacity hover:text-ink focus-visible:opacity-100 group-hover/code:opacity-100"
        >
          {copied ? (
            <Check className="size-3.5 text-success" strokeWidth={2} aria-hidden />
          ) : (
            <Copy className="size-3.5" strokeWidth={1.75} aria-hidden />
          )}
        </button>
      )}
      <pre className="overflow-x-auto rounded-md bg-inset p-3 font-mono text-xs leading-relaxed">
        <code>
          {tokens.map((token, index) => (
            <span key={index} className={TOKEN_CLASS[token.kind]}>
              {token.text}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
