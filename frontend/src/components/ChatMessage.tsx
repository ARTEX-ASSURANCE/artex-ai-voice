// artex_agent/frontend/src/components/ChatMessage.tsx
import React from 'react'; // Ensure React is imported
import { cn } from '@/lib/utils'; // For combining class names, from shadcn/ui setup

export type MessageSender = 'user' | 'agent' | 'system'; // Added 'system' for potential system messages

export interface ChatMessageProps {
  id?: string; // Optional unique ID for the message
  sender: MessageSender;
  text: string;
  timestamp?: string; // Or Date object, to be formatted
  // avatar?: string; // Optional avatar URL
}

const ChatMessage: React.FC<ChatMessageProps> = ({ sender, text, timestamp }) => {
  const isUser = sender === 'user';
  const isAgent = sender === 'agent';
  const isSystem = sender === 'system';

  // Base message bubble styles
  const baseBubbleClasses = "max-w-xs md:max-w-md lg:max-w-lg xl:max-w-xl p-3 rounded-lg shadow";

  // Conditional alignment and colors
  const alignmentClasses = isUser ? "ml-auto" : "mr-auto";

  let bubbleColorClasses = "";
  if (isUser) {
    // User messages: Primary color background, inverse text
    bubbleColorClasses = "bg-art-primary text-art-text-inverse";
  } else if (isAgent) {
    // Agent messages: Card-like background (e.g., white or light gray), primary text
    // Using a light background, slightly different from main page bg for contrast
    bubbleColorClasses = "bg-white text-art-text-primary border border-art-borders-ui";
  } else { // System messages
    bubbleColorClasses = "bg-art-background text-art-text-primary/70 italic text-sm"; // Muted, italic
    // System messages could span full width or be centered, for now, same as agent
  }

  return (
    <div className={cn(
      "flex mb-4",
      isUser ? "justify-end" : "justify-start",
      isSystem ? "justify-center" : "" // Center system messages
    )}>
      <div className={cn(
        baseBubbleClasses,
        alignmentClasses,
        bubbleColorClasses,
        isSystem ? "text-center max-w-full w-auto px-4 py-1" : "" // System messages specific styling
      )}>
        {/* Optional: Display sender name for agent messages if desired */}
        {/* {isAgent && <p className="text-xs font-semibold mb-1">Jules (Agent ARTEX)</p>} */}

        {/* Using <p> for text to allow for future markdown rendering perhaps */}
        <p className="text-sm whitespace-pre-wrap">{text}</p>

        {timestamp && !isSystem && (
          <p className={cn(
            "text-xs mt-1",
            isUser ? "text-art-text-inverse/70 text-right" : "text-art-text-primary/60 text-left"
          )}>
            {timestamp}
            {/* Example: {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} */}
          </p>
        )}
      </div>
    </div>
  );
};

export default ChatMessage;
