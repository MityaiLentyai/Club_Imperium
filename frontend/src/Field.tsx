import { useRef, type ReactNode } from "react";
import { MapPin, X } from "lucide-react";

// Text field with a pin icon, a one-click clear button and an optional trailing action.
export default function Field({
  id,
  label,
  value,
  onChange,
  onSubmit,
  placeholder,
  compact,
  action,
}: {
  id?: string;
  label?: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder: string;
  compact?: boolean;
  action: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <form
      className={`field ${compact ? "compact" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <MapPin size={compact ? 16 : 18} />
      <input
        ref={input}
        id={id}
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {value && (
        <button
          type="button"
          className="clear-btn"
          aria-label="Clear"
          title="Clear"
          onClick={() => {
            onChange("");
            input.current?.focus();
          }}
        >
          <X size={15} />
        </button>
      )}
      {action}
    </form>
  );
}
