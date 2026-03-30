import { ref, shallowRef, triggerRef, onUnmounted } from 'vue'

export function useWebSocket(url) {
  const messages = shallowRef([])
  const connected = ref(false)
  let ws = null

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}${url}`)
    ws.onopen = () => { connected.value = true }
    ws.onclose = () => { connected.value = false }
    ws.onmessage = (e) => {
      messages.value.push(e.data)
      triggerRef(messages)
    }
    ws.onerror = () => { connected.value = false }
  }

  function send(data) {
    if (ws?.readyState === WebSocket.OPEN) ws.send(data)
  }

  function close() {
    ws?.close()
  }

  onUnmounted(() => close())

  return { messages, connected, connect, send, close }
}
