// ════════════════════════════════════════════════
// Niv AI — API Client
// ════════════════════════════════════════════════

export class NivAPI {
  constructor(siteUrl, token) {
    this.siteUrl = siteUrl;
    this.token = token;
  }

  headers() {
    return {
      'Authorization': this.token,
      'Content-Type': 'application/json',
    };
  }

  async call(method, body = {}) {
    const res = await fetch(this.siteUrl + '/api/method/' + method, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.exception || 'API Error');
    return data.message;
  }

  async getResource(doctype, name, fields) {
    let url = this.siteUrl + '/api/resource/' + encodeURIComponent(doctype);
    if (name) url += '/' + encodeURIComponent(name);
    if (fields) url += '?fields=' + JSON.stringify(fields);
    const res = await fetch(url, { headers: this.headers() });
    const data = await res.json();
    return data.data;
  }

  async listResource(doctype, filters, fields, limit = 20) {
    let url = this.siteUrl + '/api/resource/' + encodeURIComponent(doctype);
    const params = [];
    if (filters) params.push('filters=' + encodeURIComponent(JSON.stringify(filters)));
    if (fields) params.push('fields=' + encodeURIComponent(JSON.stringify(fields)));
    params.push('limit_page_length=' + limit);
    if (params.length) url += '?' + params.join('&');
    const res = await fetch(url, { headers: this.headers() });
    const data = await res.json();
    return data.data;
  }

  // Stream chat using XHR (React Native doesn't support fetch ReadableStream)
  streamChat(message, { onToken, onTool, onError, onDone }) {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', this.siteUrl + '/api/method/niv_ai.niv_core.api.stream.stream_chat');
    xhr.setRequestHeader('Authorization', this.token);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Accept', 'text/event-stream');

    let idx = 0;
    xhr.onreadystatechange = () => {
      if (xhr.readyState >= 3) {
        const chunk = xhr.responseText.substring(idx);
        idx = xhr.responseText.length;
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const j = line.substring(6).trim();
          if (!j || j === '[DONE]') continue;
          try {
            const ev = JSON.parse(j);
            if (ev.type === 'token' && ev.content) onToken?.(ev.content);
            else if (ev.type === 'tool_call') onTool?.(ev.tool);
            else if (ev.type === 'error') onError?.(ev.content || 'Error');
          } catch (e) {}
        }
      }
      if (xhr.readyState === 4) {
        if (xhr.status >= 200 && xhr.status < 300) onDone?.();
        else onError?.('Server error: ' + xhr.status);
      }
    };
    xhr.onerror = () => onError?.('Network error');
    xhr.send(JSON.stringify({ message }));
    return xhr; // Return for cancellation
  }

  // Upload image
  async uploadImage(base64, filename) {
    return this.call('niv_ai.niv_core.api.voice.voice_chat_base64', {
      audio_base64: base64,
      filename: filename,
    });
  }

  // Get error logs (Developer Mode)
  async getErrorLogs(limit = 20) {
    return this.listResource('Error Log', [], ['name', 'method', 'error', 'creation'], limit);
  }

  // Get system info (Developer Mode)
  async getSystemInfo() {
    return this.call('frappe.client.get_count', { doctype: 'User', filters: { enabled: 1 } });
  }

  // Quick create document
  async createDoc(doctype, values) {
    const res = await fetch(this.siteUrl + '/api/resource/' + encodeURIComponent(doctype), {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(values),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.exception || 'Create failed');
    return data.data;
  }
}
