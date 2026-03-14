import { useState } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  loading?: boolean;
  placeholder?: string;
}

export default function SearchBar({
  onSearch,
  loading = false,
  placeholder = 'Search companies...',
}: SearchBarProps) {
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) onSearch(input);
  };

  return (
    <form onSubmit={handleSubmit} className="search-bar">
      <input
        type="text"
        value={input}
        onChange={e => setInput(e.target.value)}
        placeholder={placeholder}
        className="search-input"
        disabled={loading}
      />
      <button type="submit" className="search-btn" disabled={loading || !input.trim()}>
        {loading ? '...' : 'Search'}
      </button>
    </form>
  );
}
