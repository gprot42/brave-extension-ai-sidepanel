import { useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';

export default function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, alignRight: false });
  const iconRef = useRef<HTMLSpanElement>(null);

  const handleEnter = useCallback(() => {
    if (iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect();
      const alignRight = rect.left > window.innerWidth * 0.6;
      setPos({
        top: rect.bottom + 6,
        left: alignRight ? rect.right : rect.left,
        alignRight,
      });
    }
    setShow(true);
  }, []);

  return (
    <span className="inline-block">
      <span
        ref={iconRef}
        className="cursor-help text-gray-500 hover:text-gray-300 text-[10px] ml-1"
        onMouseEnter={handleEnter}
        onMouseLeave={() => setShow(false)}
      >
        &#9432;
      </span>
      {show && createPortal(
        <div
          style={{
            position: 'fixed',
            zIndex: 9999,
            top: pos.top,
            left: pos.alignRight ? undefined : pos.left,
            right: pos.alignRight ? window.innerWidth - pos.left : undefined,
          }}
          className="w-48 px-2 py-1.5 text-[10px] text-gray-200 bg-gray-800 border border-gray-700 rounded shadow-lg leading-tight pointer-events-none"
        >
          {text}
        </div>,
        document.body
      )}
    </span>
  );
}
