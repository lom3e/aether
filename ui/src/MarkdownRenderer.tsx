import React, { useState } from 'react';
import { Copy, Check, ExternalLink } from 'lucide-react';
import { useTranslation } from './i18n';

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  const blocks = parseMarkdownBlocks(content);

  return (
    <div className="markdown-content" style={{ lineHeight: 1.65, fontSize: '13.5px', color: 'hsl(var(--fg))' }}>
      {blocks.map((block, index) => (
        <React.Fragment key={index}>{renderBlock(block)}</React.Fragment>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Entity Decoding & Syntax Normalization (Precision 4: Safe decode outside code)
// ---------------------------------------------------------------------------

function safeDecodeEntities(str: string): string {
  if (!str) return '';
  // Hexadecimal entities: &#x47; -> G
  let decoded = str.replace(/&#x([0-9a-fA-F]+);/g, (match, hex) => {
    try {
      const code = parseInt(hex, 16);
      return String.fromCodePoint(code);
    } catch {
      return match;
    }
  });

  // Decimal entities: &#71; -> G
  decoded = decoded.replace(/&#([0-9]+);/g, (match, dec) => {
    try {
      const code = parseInt(dec, 10);
      return String.fromCodePoint(code);
    } catch {
      return match;
    }
  });

  // Standard safe entities
  const entityMap: Record<string, string> = {
    '&quot;': '"',
    '&apos;': "'",
    '&#39;': "'",
    '&nbsp;': ' ',
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
  };
  return decoded.replace(/&(?:quot|apos|#39|nbsp|amp|lt|gt);/g, m => entityMap[m] || m);
}

function normalizeMarkdownLine(line: string): string {
  // Normalize escaped markdown characters: \# -> #, \* -> *, \_ -> _, \- -> -, \` -> `, \> -> >
  const unescaped = line.replace(/\\([#*_`>~\[\]\(\)\-])/g, '$1');
  return safeDecodeEntities(unescaped);
}

// ---------------------------------------------------------------------------
// Block Parsing & Data Structures
// ---------------------------------------------------------------------------

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'code'; language: string; code: string }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'blockquote'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'divider' };

function parseMarkdownBlocks(rawText: string): Block[] {
  // Normalize line endings and break tags
  const sanitized = rawText
    .replace(/\r\n/g, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<hr\s*\/?>/gi, '\n---\n');

  const lines = sanitized.split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];

    // 1. Fenced Code Blocks (Preserved completely literal without unescaping)
    if (rawLine.trim().startsWith('```')) {
      const language = rawLine.trim().replace(/^```/, '').trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: 'code', language, code: codeLines.join('\n') });
      continue;
    }

    const line = normalizeMarkdownLine(rawLine);

    // 2. Horizontal Rules
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      blocks.push({ type: 'divider' });
      i++;
      continue;
    }

    // 3. Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      i++;
      continue;
    }

    // 4. Blockquotes
    if (line.trim().startsWith('>')) {
      const quoteLines: string[] = [];
      while (i < lines.length) {
        const curLine = normalizeMarkdownLine(lines[i]);
        if (!curLine.trim().startsWith('>')) break;
        quoteLines.push(curLine.replace(/^>\s?/, ''));
        i++;
      }
      blocks.push({ type: 'blockquote', text: quoteLines.join(' ') });
      continue;
    }

    // 5. Tables
    if (line.includes('|') && i + 1 < lines.length) {
      const nextLine = normalizeMarkdownLine(lines[i + 1]);
      if (nextLine.includes('|') && /[-:]+/.test(nextLine)) {
        const headers = parseTableRow(line);
        i += 2; // skip header and separator
        const rows: string[][] = [];
        while (i < lines.length) {
          const rowLine = normalizeMarkdownLine(lines[i]);
          if (!rowLine.includes('|')) break;
          const row = parseTableRow(rowLine);
          if (row.length > 0) rows.push(row);
          i++;
        }
        blocks.push({ type: 'table', headers, rows });
        continue;
      }
    }

    // 6. Unordered List
    if (/^[*+-]\s+/.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length) {
        const curLine = normalizeMarkdownLine(lines[i]);
        if (!/^[*+-]\s+/.test(curLine.trim())) break;
        items.push(curLine.trim().replace(/^[*+-]\s+/, ''));
        i++;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }

    // 7. Ordered List
    if (/^\d+\.\s+/.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length) {
        const curLine = normalizeMarkdownLine(lines[i]);
        if (!/^\d+\.\s+/.test(curLine.trim())) break;
        items.push(curLine.trim().replace(/^\d+\.\s+/, ''));
        i++;
      }
      blocks.push({ type: 'ol', items });
      continue;
    }

    // 8. Empty lines
    if (!line.trim()) {
      i++;
      continue;
    }

    // 9. Regular Paragraph
    const paraLines: string[] = [];
    while (i < lines.length) {
      if (lines[i].trim().startsWith('```')) break;
      const curNorm = normalizeMarkdownLine(lines[i]);
      if (
        !curNorm.trim() ||
        curNorm.trim().startsWith('#') ||
        curNorm.trim().startsWith('>') ||
        /^[*+-]\s+/.test(curNorm.trim()) ||
        /^\d+\.\s+/.test(curNorm.trim()) ||
        (curNorm.includes('|') && i + 1 < lines.length && normalizeMarkdownLine(lines[i + 1]).includes('|') && /[-:]+/.test(normalizeMarkdownLine(lines[i + 1])))
      ) {
        break;
      }
      paraLines.push(curNorm);
      i++;
    }
    if (paraLines.length > 0) {
      blocks.push({ type: 'paragraph', text: paraLines.join('\n') });
    }
  }

  return blocks;
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim());
}

// ---------------------------------------------------------------------------
// Block Rendering
// ---------------------------------------------------------------------------

function renderBlock(block: Block): React.ReactNode {
  switch (block.type) {
    case 'heading': {
      const Tag = `h${Math.min(block.level + 1, 6)}` as keyof React.JSX.IntrinsicElements;
      const size = block.level === 1 ? '17px' : block.level === 2 ? '15px' : '14px';
      const weight = block.level <= 2 ? 600 : 500;
      return (
        <Tag style={{ fontSize: size, fontWeight: weight, margin: '14px 0 6px', color: 'hsl(var(--fg))' }}>
          {renderInline(block.text)}
        </Tag>
      );
    }

    case 'code':
      return <CodeBlock code={block.code} language={block.language} />;

    case 'table':
      return (
        <div style={{ overflowX: 'auto', margin: '12px 0', border: '1px solid hsl(var(--border))', borderRadius: '8px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: 'hsl(var(--muted)/0.5)', borderBottom: '1px solid hsl(var(--border))' }}>
                {block.headers.map((th, idx) => (
                  <th key={idx} style={{ padding: '8px 12px', fontWeight: 600 }}>
                    {renderInline(th)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rIdx) => (
                <tr
                  key={rIdx}
                  style={{
                    borderBottom: rIdx < block.rows.length - 1 ? '1px solid hsl(var(--border)/0.5)' : 'none',
                    backgroundColor: rIdx % 2 === 1 ? 'hsl(var(--muted)/0.15)' : 'transparent',
                  }}
                >
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} style={{ padding: '8px 12px' }}>
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    case 'ul':
      return (
        <ul style={{ margin: '8px 0', paddingLeft: '20px', listStyleType: 'disc' }}>
          {block.items.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '4px' }}>
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );

    case 'ol':
      return (
        <ol style={{ margin: '8px 0', paddingLeft: '20px', listStyleType: 'decimal' }}>
          {block.items.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '4px' }}>
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );

    case 'blockquote':
      return (
        <blockquote
          style={{
            margin: '10px 0',
            padding: '8px 14px',
            borderLeft: '3px solid hsl(var(--primary))',
            backgroundColor: 'hsl(var(--primary)/0.05)',
            borderRadius: '0 6px 6px 0',
            color: 'hsl(var(--muted-fg))',
            fontStyle: 'italic',
          }}
        >
          {renderInline(block.text)}
        </blockquote>
      );

    case 'divider':
      return <hr style={{ border: 'none', borderTop: '1px solid hsl(var(--border))', margin: '14px 0' }} />;

    case 'paragraph':
      return (
        <p style={{ margin: '6px 0', whiteSpace: 'pre-wrap' }}>
          {renderInline(block.text)}
        </p>
      );
  }
}

// ---------------------------------------------------------------------------
// Code Block with Copy Action
// ---------------------------------------------------------------------------

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div
      style={{
        margin: '10px 0',
        borderRadius: '8px',
        border: '1px solid hsl(var(--border))',
        backgroundColor: 'hsl(var(--muted)/0.3)',
        overflow: 'hidden',
        fontSize: '12.5px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 10px',
          borderBottom: '1px solid hsl(var(--border)/0.5)',
          backgroundColor: 'hsl(var(--muted)/0.5)',
          fontSize: '11px',
          fontFamily: 'var(--font-mono)',
          color: 'hsl(var(--muted-fg))',
        }}
      >
        <span>{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="btn btn-ghost"
          style={{ padding: '2px 6px', fontSize: '11px', gap: '4px', height: '22px' }}
        >
          {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
          <span>{copied ? t('copied') : t('copyText')}</span>
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: '12px 14px',
          overflowX: 'auto',
          fontFamily: 'var(--font-mono)',
          lineHeight: 1.5,
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline Renderer (Links, Code, Bold, Italic, Strikethrough)
// ---------------------------------------------------------------------------

function renderInline(text: string): React.ReactNode {
  if (!text) return null;

  // 1. Split by inline code: `code`
  const codeParts = text.split(/(`[^`]+`)/g);

  return codeParts.map((part, pIdx) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={pIdx}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.9em',
            padding: '2px 5px',
            borderRadius: '4px',
            backgroundColor: 'hsl(var(--muted))',
            color: 'hsl(var(--primary))',
          }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    // 2. Parse Markdown Links: [label](url)
    const linkParts = part.split(/(\[[^\]]+\]\([^\)]+\))/g);

    return (
      <React.Fragment key={pIdx}>
        {linkParts.map((lPart, lIdx) => {
          const linkMatch = lPart.match(/^\[([^\]]+)\]\(([^\)]+)\)$/);
          if (linkMatch) {
            const [, linkLabel, linkUrl] = linkMatch;
            const isExternal = linkUrl.startsWith('http://') || linkUrl.startsWith('https://');
            return (
              <a
                key={lIdx}
                href={linkUrl}
                target={isExternal ? '_blank' : undefined}
                rel={isExternal ? 'noopener noreferrer' : undefined}
                style={{
                  color: 'hsl(var(--primary))',
                  textDecoration: 'underline',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '2px',
                }}
              >
                <span>{linkLabel}</span>
                {isExternal && <ExternalLink size={10} style={{ opacity: 0.7 }} />}
              </a>
            );
          }

          // 3. Bold, Italic, Strikethrough
          const formattedParts = lPart.split(/(\*\*[^*]+\*\*|\*[^*]+\*|__[^_]+__|~~[^~]+~~)/g);

          return (
            <React.Fragment key={lIdx}>
              {formattedParts.map((fPart, fIdx) => {
                if ((fPart.startsWith('**') && fPart.endsWith('**')) || (fPart.startsWith('__') && fPart.endsWith('__'))) {
                  return <strong key={fIdx}>{fPart.slice(2, -2)}</strong>;
                }
                if (fPart.startsWith('*') && fPart.endsWith('*') && fPart.length > 2) {
                  return <em key={fIdx}>{fPart.slice(1, -1)}</em>;
                }
                if (fPart.startsWith('~~') && fPart.endsWith('~~') && fPart.length > 4) {
                  return <s key={fIdx}>{fPart.slice(2, -2)}</s>;
                }
                return fPart;
              })}
            </React.Fragment>
          );
        })}
      </React.Fragment>
    );
  });
}
