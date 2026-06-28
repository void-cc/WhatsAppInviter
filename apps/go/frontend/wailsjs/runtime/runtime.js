// @ts-nocheck
/* Wails runtime — minimal stub for dev; replaced by wails generate module */

export function EventsOn(eventName, callback) {
  if (window.runtime?.EventsOn) {
    return window.runtime.EventsOn(eventName, callback);
  }
  window.addEventListener('wails:' + eventName, (e) => callback(e.detail));
}

export function EventsEmit(eventName, data) {
  window.dispatchEvent(new CustomEvent('wails:' + eventName, { detail: data }));
}

export function Quit() {
  window.runtime?.Quit?.();
}
