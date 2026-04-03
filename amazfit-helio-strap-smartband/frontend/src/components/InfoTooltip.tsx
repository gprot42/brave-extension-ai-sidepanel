import { useState, useRef, useEffect } from 'react';

export default function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  const iconRef = useRef<HTMLSpanElement>(null);
  const [alignRight, setAlignRight] = useState(false);

  useEffect(() => {
    if (show && iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect();
      // If icon is in the left 40% of viewport, align tooltip to the left edge
      setAlignRight(rect.left > window.innerWidth * 0.6);
    }
  }, [show]);

  const posClass = alignRight
    ? 'right-0'
    : 'left-0';

  return (
    <span className="relative inline-block">
      <span
        ref={iconRef}
        className="cursor-help text-gray-500 hover:text-gray-300 text-[10px] ml-1"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
      >
        &#9432;
      </span>
      {show && (
        <div className={`absolute z-50 bottom-full ${posClass} mb-1 w-48 px-2 py-1.5 text-[10px] text-gray-200 bg-gray-800 border border-gray-700 rounded shadow-lg leading-tight`}>
          {text}
        </div>
      )}
    </span>
  );
}
