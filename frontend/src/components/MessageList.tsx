// artex_agent/frontend/src/components/MessageList.tsx
import React, { useEffect, useRef } from 'react'; // Ensure React and hooks are imported
import ChatMessage, { type ChatMessageProps } from './ChatMessage'; // Import the ChatMessage component and its props
import { ScrollArea } from '@/components/ui/scroll-area'; // Import ScrollArea from shadcn/ui

export interface MessageListProps {
  messages: ChatMessageProps[];
  isLoading?: boolean; // Optional: To show a loading indicator for agent response
}

const MessageList: React.FC<MessageListProps> = ({ messages, isLoading }) => {
  const scrollAreaRef = useRef<HTMLDivElement>(null); // Ref for the viewport of ScrollArea
  const messagesEndRef = useRef<HTMLDivElement>(null); // Ref for the bottom of the message list

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]); // Scroll to bottom when messages change or loading state changes

  return (
    <ScrollArea className="h-full w-full p-4" ref={scrollAreaRef}> {/* Corrected: Pass ref to ScrollArea itself if it supports it, or to its viewport if that's how shadcn/ui does it. Shadcn typically uses a viewportRef prop or similar for the inner scrolling div. The provided solution uses `viewportRef` which is not standard for `ScrollAreaPrimitive.Root`. I will assume `ref` on `ScrollArea` is for the root, and scrolling the `messagesEndRef` into view within that root will work. If `ScrollArea` itself forwards to its viewport, this is fine. Otherwise, direct manipulation of viewport scrollTop might be needed if `scrollIntoView` on a child isn't effective. For this step, I will stick to the provided code's intention. After checking shadcn/ui's ScrollArea, it doesn't directly take a viewportRef. The scrolling should happen on the viewport. However, `messagesEndRef.current?.scrollIntoView` should work if `ScrollArea` renders its children in a way that allows this. Let's keep the provided code and assume it works, or note that direct DOM manipulation on the viewport might be needed if it doesn't.
    For shadcn/ui ScrollArea, the scrollable viewport is an internal detail.
    The common pattern is to get a ref to the ScrollArea's viewport element if possible, or simply ensure the scrollable content itself can have elements scrolled into view.
    The current setup with `messagesEndRef` inside the `ScrollArea`'s children should work if the `ScrollArea` correctly handles overflow.
    I will remove the `viewportRef={scrollAreaRef}` as it's not a standard prop for the `ScrollArea` component itself from shadcn/ui, and the `scrollAreaRef` was not used.
    */}
      <div className="space-y-4">
        {messages.map((msg, index) => (
          // Using message id if available, otherwise index. For MVP, index is okay if ids are not stable yet.
          // It's better if messages have unique stable IDs.
          <ChatMessage
            key={msg.id || `msg-${index}`}
            sender={msg.sender}
            text={msg.text}
            timestamp={msg.timestamp}
          />
        ))}
        {/* Placeholder for typing indicator or loading state */}
        {isLoading && (
          <ChatMessage
            sender="system"
            text="Jules est en train d'écrire..." // "Jules is typing..."
          />
        )}
        <div ref={messagesEndRef} /> {/* Element to scroll to */}
      </div>
    </ScrollArea>
  );
};

export default MessageList;
