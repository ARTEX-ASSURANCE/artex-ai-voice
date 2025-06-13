// artex_agent/frontend/src/components/InputArea.tsx
import React, { useState, KeyboardEvent } from 'react';
import { Input } from '@/components/ui/input'; // Assuming shadcn/ui Input is available
import { Button } from '@/components/ui/button'; // Assuming shadcn/ui Button is available
// import { Mic, SendHorizonal } from 'lucide-react'; // Example icons for future use

export interface InputAreaProps {
  onSendMessage: (message: string) => void;
  isLoading?: boolean; // To disable input/button while agent is replying
}

const InputArea: React.FC<InputAreaProps> = ({ onSendMessage, isLoading }) => {
  const [inputValue, setInputValue] = useState('');

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(event.target.value);
  };

  const handleSendMessage = () => {
    if (inputValue.trim() && !isLoading) {
      onSendMessage(inputValue.trim());
      setInputValue(''); // Clear input after sending
    }
  };

  const handleKeyPress = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault(); // Prevent newline in input on Enter
      handleSendMessage();
    }
  };

  return (
    <div className="flex items-center space-x-2 p-2 bg-white border-t border-art-borders-ui">
      {/* Placeholder for Voice Input Toggle Button - Future Feature
      <Button variant="ghost" size="icon" disabled={isLoading}>
        <Mic className="h-5 w-5 text-art-primary" />
      </Button>
      */}

      <Input
        type="text"
        placeholder="Écrivez votre message ici..." // "Write your message here..."
        value={inputValue}
        onChange={handleInputChange}
        onKeyPress={handleKeyPress}
        disabled={isLoading}
        className="flex-grow focus-visible:ring-art-accent focus-visible:ring-1 focus-visible:ring-offset-0"
        // Added focus styling using art-accent
      />
      <Button
        onClick={handleSendMessage}
        disabled={isLoading || !inputValue.trim()}
        // className="bg-art-primary hover:bg-art-primary/90 text-art-text-inverse" // Already default button style from shadcn/ui if primary is themed
      >
        Envoyer
        {/* <SendHorizonal className="ml-2 h-4 w-4" /> // Example icon */}
      </Button>
    </div>
  );
};

export default InputArea;
