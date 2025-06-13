// artex_agent/frontend/src/App.tsx
import React, { useState, useEffect } from 'react';
import MessageList from './components/MessageList';
import InputArea from './components/InputArea';
import { type ChatMessageProps, type MessageSender } from './components/ChatMessage';
// Removed 'cn' import as it's not used directly in this App.tsx version

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";

function App() {
  const [messages, setMessages] = useState<ChatMessageProps[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  // Generate a simple session ID for MVP. In a real app, this might be more robust or come from auth.
  const [sessionId] = useState<string>(`session_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`);

  // Effect for initial welcome message
  useEffect(() => {
    setMessages([
      {
        id: `agent-welcome-${Date.now()}`,
        sender: 'agent',
        text: "Bonjour ! Je suis Jules, votre assistant ARTEX. Comment puis-je vous aider aujourd'hui ?",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ]);
  }, []);

  const handleSendMessage = async (messageText: string) => {
    if (!messageText.trim()) return;

    const userMessage: ChatMessageProps = {
      id: `user-${Date.now()}-${Math.random().toString(36).substring(2,7)}`, // More unique ID
      sender: 'user',
      text: messageText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setIsLoading(true);

    let systemErrorText: string | null = null;

    try {
      const response = await fetch(`${API_BASE_URL}/chat/send_message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          user_message: messageText, // Changed line
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Unknown server error." }));
        console.error("API Error:", response.status, errorData);
        systemErrorText = `Erreur de communication avec le serveur : ${errorData.detail || response.statusText}`;
      } else {
        const data = await response.json(); // Assuming backend sends ChatMessageResponse
        const agentMessage: ChatMessageProps = {
          id: `agent-${Date.now()}-${Math.random().toString(36).substring(2,7)}`, // More unique ID
          sender: 'agent',
          text: data.agent_response,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages(prevMessages => [...prevMessages, agentMessage]);
        setConversationId(data.conversation_id);
      }
    } catch (error) {
      console.error("Failed to send message or parse response:", error);
      systemErrorText = "Une erreur de réseau est survenue. Veuillez vérifier votre connexion et réessayer.";
    } finally {
      setIsLoading(false);
      if (systemErrorText) {
        const systemErrorMessage: ChatMessageProps = {
          id: `syserr-${Date.now()}-${Math.random().toString(36).substring(2,7)}`,
          sender: 'system',
          text: systemErrorText,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages(prevMessages => [...prevMessages, systemErrorMessage]);
      }
    }
  };

  return (
    <div className="flex flex-col h-screen bg-art-background text-art-text-primary">
      <header className="bg-art-primary text-art-text-inverse p-3 shadow-md flex items-center shrink-0">
        {/* <img src="/artex-logo-white.svg" alt="ARTEX Logo" className="h-8 mr-3" /> Placeholder */}
        <h1 className="text-lg font-semibold">Jules - Assistant ARTEX</h1>
      </header>

      {/* Ensure main area takes up available space and MessageList handles its own scrolling */}
      <main className="flex-grow overflow-hidden flex flex-col">
        <MessageList messages={messages} isLoading={isLoading} />
      </main>

      <footer className="border-t border-art-borders-ui shrink-0">
        <InputArea onSendMessage={handleSendMessage} isLoading={isLoading} />
      </footer>
    </div>
  );
}

export default App;
