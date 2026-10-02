import { useEffect, useRef, useState } from "react";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  readonly [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionResultListLike {
  readonly length: number;
  readonly [index: number]: SpeechRecognitionResultLike;
}

interface SpeechRecognitionResultEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListLike;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onstart: (() => void) | null;
  onend: (() => void) | null;
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
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const stopRequestedRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const isSupported =
    typeof window !== "undefined" &&
    Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition);

  const stop = () => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    stopRequestedRef.current = true;
    try {
      recognition.stop();
    } catch (caught) {
      if (!(caught instanceof DOMException) || caught.name !== "InvalidStateError") {
        throw caught;
      }
      recognitionRef.current = null;
      setIsListening(false);
    }
  };

  const start = () => {
    if (recognitionRef.current) return;
    const Constructor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Constructor) {
      setError("Voice input is not available in this browser.");
      return;
    }

    setError(null);
    const recognition = new Constructor();
    let hasResult = false;
    let hasError = false;
    const processedResultIndexes = new Set<number>();
    stopRequestedRef.current = false;
    recognition.lang = language;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      const finalTranscript = [];
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal && !processedResultIndexes.has(index)) {
          processedResultIndexes.add(index);
          finalTranscript.push(result[0].transcript.trim());
        }
      }
      const transcript = finalTranscript.filter(Boolean).join(" ");
      if (transcript) {
        hasResult = true;
        onTranscriptRef.current(transcript);
      }
    };
    recognition.onerror = (event) => {
      hasError = true;
      if (stopRequestedRef.current && event.error === "aborted") return;
      const messages: Record<string, string> = {
        "not-allowed": "Microphone access was denied. Allow microphone access and try again.",
        "service-not-allowed": "Microphone access was denied. Allow microphone access and try again.",
        "audio-capture": "No microphone was found. Connect a microphone and try again.",
        "no-speech": "No speech was detected. Try speaking and tap the microphone again.",
        network: "Voice recognition could not connect. Check your internet connection and try again.",
        aborted: "Voice recognition was stopped.",
      };
      setError(messages[event.error] ?? "Voice recognition failed. Please try again.");
      setIsListening(false);
    };
    recognition.onend = () => {
      if (recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      setIsListening(false);
      if (!hasResult && !hasError && !stopRequestedRef.current) {
        setError("No speech was detected. Try speaking and tap the microphone again.");
      }
    };
    recognitionRef.current = recognition;
    setIsListening(true);
    try {
      recognition.start();
    } catch (caught) {
      recognitionRef.current = null;
      setIsListening(false);
      if (caught instanceof DOMException && caught.name === "NotAllowedError") {
        setError("Microphone access was denied. Allow microphone access and try again.");
      } else if (caught instanceof DOMException && caught.name === "InvalidStateError") {
        setError("Voice recognition is already starting. Please wait and try again.");
      } else {
        setError("Voice recognition could not start. Check microphone permissions and try again.");
      }
    }
  };

  useEffect(
    () => () => {
      const recognition = recognitionRef.current;
      recognitionRef.current = null;
      recognition?.stop();
    },
    []
  );

  return { error, isListening, isSupported, start, stop };
}
