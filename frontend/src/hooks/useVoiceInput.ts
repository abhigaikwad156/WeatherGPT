import { useState } from "react";

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export function useVoiceInput(onTranscript: (text: string) => void, language: string) {
  const [isListening, setIsListening] = useState(false);
  const [isSupported] = useState(
    () => Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition)
  );

  const start = () => {
    const Constructor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Constructor) return;
    const recognition = new Constructor();
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => onTranscript(event.results[0][0].transcript);
    recognition.onerror = () => setIsListening(false);
    recognition.start();
    setIsListening(true);
  };

  return { isListening, isSupported, start };
}
