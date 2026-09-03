"use client";

import { Fragment, useState } from "react";
import { appService, getAuthenticatedMediaBlobUrl } from "@/lib/api";

const audioCache = new Map<string, string>();
const TAG_PATTERN = /\[\[(pronounce|grammar|vocab|highlight|correction):([^\]]+)\]\]/gi;

type TagType = "pronounce" | "grammar" | "vocab" | "highlight" | "correction";

type Part =
  | { kind: "text"; value: string }
  | { kind: "tag"; tagType: TagType; value: string };

type Props = {
  text: string;
  className?: string;
};

export function PronunciationText({ text, className }: Props) {
  const [loadingWord, setLoadingWord] = useState<string | null>(null);
  const [playingWord, setPlayingWord] = useState<string | null>(null);

  async function play(word: string) {
    const normalized = word.trim();
    if (!normalized || loadingWord) return;

    setLoadingWord(normalized);
    try {
      let blobUrl = audioCache.get(normalized.toLowerCase());
      if (!blobUrl) {
        blobUrl = await getAuthenticatedMediaBlobUrl(appService.getPronunciationAudioUrl(normalized)) || undefined;
        if (!blobUrl) return;
        audioCache.set(normalized.toLowerCase(), blobUrl);
      }

      const audio = new Audio(blobUrl);
      setPlayingWord(normalized);
      audio.onended = () => setPlayingWord(null);
      audio.onerror = () => setPlayingWord(null);
      await audio.play();
    } finally {
      setLoadingWord(null);
    }
  }

  const parts: Part[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(TAG_PATTERN)) {
    if (match.index! > lastIndex) {
      parts.push({ kind: "text", value: text.slice(lastIndex, match.index) });
    }
    const tagType = match[1].toLowerCase() as TagType;
    parts.push({ kind: "tag", tagType, value: match[2].trim() });
    lastIndex = match.index! + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push({ kind: "text", value: text.slice(lastIndex) });
  }

  return (
    <span className={className}>
      {parts.map((part, index) => {
        if (part.kind === "text") {
          return <Fragment key={index}>{part.value}</Fragment>;
        }

        if (part.tagType === "pronounce") {
          return (
            <button
              key={index}
              type="button"
              onClick={() => play(part.value)}
              aria-label={`Listen to the pronunciation of ${part.value}`}
              className="mx-0.5 inline-flex items-center gap-1 rounded-lg border border-rally/25 bg-rally-mist px-2 py-0.5 text-xs font-semibold text-rally-deep shadow-xs transition hover:border-rally/50 hover:bg-rally-mist/70 disabled:opacity-60 align-baseline cursor-pointer"
              disabled={loadingWord === part.value}
            >
              <span aria-hidden="true">{loadingWord === part.value ? "…" : playingWord === part.value ? "◼" : "▶"}</span>
              <span>{part.value}</span>
            </button>
          );
        }

        if (part.tagType === "grammar") {
          return (
            <span
              key={index}
              className="mx-0.5 inline-flex items-center gap-1.5 rounded-lg border border-fuchsia-300 bg-fuchsia-50/90 px-2 py-0.5 text-xs font-semibold text-fuchsia-950 shadow-xs align-baseline"
              title="Grammar insight"
            >
              <span className="text-[9px] font-bold uppercase tracking-wider text-fuchsia-700 bg-fuchsia-200/80 px-1 py-0.5 rounded leading-none">
                grammar
              </span>
              <span>{part.value}</span>
            </span>
          );
        }

        if (part.tagType === "vocab") {
          return (
            <span
              key={index}
              className="mx-0.5 inline-flex items-center gap-1.5 rounded-lg border border-teal-300 bg-teal-50/90 px-2 py-0.5 text-xs font-semibold text-teal-950 shadow-xs align-baseline"
              title="Vocabulary alternative"
            >
              <span className="text-[9px] font-bold uppercase tracking-wider text-teal-700 bg-teal-200/80 px-1 py-0.5 rounded leading-none">
                vocab
              </span>
              <span>{part.value}</span>
            </span>
          );
        }

        if (part.tagType === "highlight") {
          return (
            <mark
              key={index}
              className="mx-0.5 rounded-md bg-amber-100/90 border border-amber-300/70 px-1.5 py-0.5 text-xs font-semibold text-amber-950 align-baseline"
            >
              {part.value}
            </mark>
          );
        }

        if (part.tagType === "correction") {
          return (
            <span
              key={index}
              className="mx-0.5 inline-flex items-center gap-1.5 rounded-lg border border-sky-300 bg-sky-50/90 px-2 py-0.5 text-xs font-semibold text-sky-950 shadow-xs align-baseline"
              title="Coaching tip"
            >
              <span className="text-[9px] font-bold uppercase tracking-wider text-sky-700 bg-sky-200/80 px-1 py-0.5 rounded leading-none">
                tip
              </span>
              <span>{part.value}</span>
            </span>
          );
        }

        return <Fragment key={index}>{part.value}</Fragment>;
      })}
    </span>
  );
}
