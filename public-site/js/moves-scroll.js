/**
 * Pin a moves list to its absolute bottom after layout (live-follow).
 * Two rAF ticks catch font/board height changes that happen after paint.
 */

export function pinScrollToBottom(el) {
  if (!el) return;
  const pin = () => {
    el.scrollTop = el.scrollHeight;
  };
  pin();
  requestAnimationFrame(() => {
    pin();
    requestAnimationFrame(pin);
  });
}
