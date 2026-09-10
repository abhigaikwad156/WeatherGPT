import { type FormEvent, useState } from "react";

import type { ChatMessage } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { AlertCard, RecommendationCard, WeatherCard } from "../components/dataCards";
import { ErrorState, LoadingState } from "../components/ui";
import { useVoiceInput } from "../hooks/useVoiceInput";

export function ChatPage() {
  const [language, setLanguage] = useState("mr-IN");
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const voice = useVoiceInput((transcript) => setText((current) => `${current} ${transcript}`.trim()), language);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!text.trim()) return;
    setSending(true); setError(null);
    try { const response = await weatherGptApi.sendMessage({ content: text.trim(), language, conversationId }); setConversationId(response.conversationId); setMessages((current) => [...current, response.message]); setText(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to send your message."); }
    finally { setSending(false); }
  };
  return <div className="page chat-page"><header className="page-header"><div><p className="eyebrow">Conversational help</p><h1>Ask WeatherGPT</h1><p>Ask in Marathi, Hindi, or English. Advice comes from backend data and decision rules.</p></div><label className="language-select">Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="mr-IN">मराठी</option><option value="hi-IN">हिन्दी</option><option value="en-IN">English</option></select></label></header><section className="chat-thread" aria-live="polite">{messages.length === 0 && <div className="chat-welcome"><span>🌦</span><h2>How can I help with your farm today?</h2><p>For example: “माझ्या कांद्याला आज पाणी द्यावे का?”</p></div>}{messages.map((message) => <article key={message.id} className={`message message-${message.role}`}><p>{message.content}</p>{message.cards?.map((card, index) => <div className="chat-card" key={`${message.id}-${index}`}>{card.recommendation && <RecommendationCard recommendation={card.recommendation} />}{card.weather && <WeatherCard weather={card.weather} />}{card.alert && <AlertCard alert={card.alert} />}</div>)}</article>)}{sending && <LoadingState label="WeatherGPT is checking your farm data…" />}{error && <ErrorState message={error} />}</section><form className="chat-composer" onSubmit={submit}><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Type your question…" aria-label="Your weather question" rows={2} /><div><button type="button" className="secondary-button" disabled={!voice.isSupported || voice.isListening} onClick={voice.start}>{voice.isListening ? "Listening…" : "🎙 Voice"}</button><button className="primary-button" disabled={sending || !text.trim()}>Send</button></div>{!voice.isSupported && <small>Voice input is not available in this browser.</small>}</form></div>;
}
