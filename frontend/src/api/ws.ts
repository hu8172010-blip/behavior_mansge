let socket: WebSocket | null = null;
let onMessageCallback: ((data: any) => void) | null = null;
let reconnectTimer: number | null = null;

export function connectPermissionSocket(token: string, onMessage: (data: any) => void) {
  if (socket) return;
  onMessageCallback = onMessage;

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/api/v1/ws/permissions?token=${encodeURIComponent(token)}`;

  socket = new WebSocket(url);

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessageCallback?.(data);
    } catch {
      // ignore malformed messages
    }
  };

  socket.onerror = () => {
    socket?.close();
  };

  socket.onclose = () => {
    socket = null;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    reconnectTimer = window.setTimeout(() => {
      if (token && onMessageCallback) {
        connectPermissionSocket(token, onMessageCallback);
      }
    }, 3000);
  };
}

export function disconnectPermissionSocket() {
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  onMessageCallback = null;
}
