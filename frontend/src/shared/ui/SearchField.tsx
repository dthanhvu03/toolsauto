import { inputClass, primaryBtnClass } from "@/shared/ui/controls";

export function SearchField({
  placeholder,
  value,
  onChange,
  onSubmit,
}: {
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <>
      <input
        className={inputClass}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSubmit();
        }}
      />
      <button type="button" className={primaryBtnClass} onClick={onSubmit}>
        Tìm
      </button>
    </>
  );
}
