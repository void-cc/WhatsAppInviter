export function EventsOn(
  eventName: string,
  callback: (...args: unknown[]) => void,
): () => void;

export function EventsEmit(eventName: string, ...data: unknown[]): void;

export function Quit(): void;
