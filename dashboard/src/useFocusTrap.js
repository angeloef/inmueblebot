import { useEffect, useRef } from 'react';

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])',
  'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * Accessible dialog behaviour for modals/drawers (WCAG 2.1.2 / 2.4.3):
 *  - moves focus into the dialog on open
 *  - traps Tab / Shift+Tab inside the dialog
 *  - closes on Escape (callback must be provided)
 *  - restores focus to the element that had it before opening
 *
 * The effect runs only on mount/unmount: `onClose` is read through a ref so an
 * unstable inline callback from the caller does not re-trigger the trap (which
 * would steal focus back to the first element on every parent re-render).
 *
 * Returns a ref to attach to the dialog container.
 */
export function useFocusTrap(onClose) {
  const ref = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const previouslyFocused = document.activeElement;
    let tabindexAdded = false;

    // Respect an existing autoFocus (React focuses it before this effect runs);
    // otherwise move focus to the first focusable element, or the dialog itself.
    if (!node.contains(document.activeElement)) {
      const focusables = node.querySelectorAll(FOCUSABLE);
      const first = focusables[0];
      if (first) first.focus();
      else { node.setAttribute('tabindex', '-1'); tabindexAdded = true; node.focus(); }
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current?.(); return; }
      if (e.key !== 'Tab') return;
      const items = node.querySelectorAll(FOCUSABLE);
      if (items.length === 0) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstItem) {
        e.preventDefault(); lastItem.focus();
      } else if (!e.shiftKey && document.activeElement === lastItem) {
        e.preventDefault(); firstItem.focus();
      }
    };

    node.addEventListener('keydown', handleKeyDown);
    return () => {
      node.removeEventListener('keydown', handleKeyDown);
      if (tabindexAdded) node.removeAttribute('tabindex');
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    };
  }, []);

  return ref;
}
