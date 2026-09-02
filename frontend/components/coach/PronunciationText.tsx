"use client";

import { Fragment, useState } from "react";
import { appService, getAuthenticatedMediaBlobUrl } from "@/lib/api";

const audioCache = new Map<string, string>();
const TAG_PATTERN = /\[\[pronounce:([^\]]+)\]\]/gi;

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

  const parts: Array<{ kind: "text" | "word"; value: string }> = [];
  let lastIndex = 0;
  for (const match of text.matchAll(TAG_PATTERN)) {
    if (match.index! > lastIndex) parts.push({ kind: "text", value: text.slice(lastIndex, match.index) });
    parts.push({ kind: "word", value: match[1].trim() });
    lastIndex = match.index! + match[0].length;
  }
  if (lastIndex < text.length) parts.push({ kind: "text", value: text.slice(lastIndex) });

  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.kind === "text" ? (
          <Fragment key={index}>{part.value}</Fragment>
        ) : (
          <button
            key={index}
            type="button"
            onClick={() => play(part.value)}
            aria-label={`Listen to the pronunciation of ${part.value}`}
            className="mx-0.5 inline-flex items-center gap-1 rounded-lg border border-rally/25 bg-rally-mist px-2 py-0.5 font-semibold text-rally-deep shadow-sm transition hover:border-rally/50 hover:bg-rally-mist/70 disabled:opacity-60"
            disabled={loadingWord === part.value}
          >
            <span aria-hidden="true">{loadingWord === part.value ? "…" : playingWord === part.value ? "◼" : "▶"}</span>
            <span>{part.value}</span>
          </button>
        )
      )}
    </span>
  );
}
