import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  StyleSheet, View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, StatusBar, ActivityIndicator,
  SafeAreaView, Alert, Animated, Keyboard, ScrollView,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ══════════════════════════════════════════
// THEME
// ══════════════════════════════════════════
const COLORS = {
  bg: '#1a1a2e',
  surface: '#16213e',
  surfaceLight: '#1e2a4a',
  card: '#0f3460',
  purple: '#7c3aed',
  purpleLight: '#a78bfa',
  teal: '#06b6d4',
  text: '#e2e8f0',
  textDim: '#94a3b8',
  textMuted: '#64748b',
  border: '#334155',
  error: '#ef4444',
  success: '#10b981',
  warning: '#f59e0b',
};

// ══════════════════════════════════════════
// MAIN APP
// ══════════════════════════════════════════
export default function App() {
  const [screen, setScreen] = useState('loading'); // loading, pair, chat
  const [auth, setAuth] = useState(null);
  const [config, setConfig] = useState(null);
  const [userInfo, setUserInfo] = useState(null);

  useEffect(() => {
    checkExistingAuth();
  }, []);

  const checkExistingAuth = async () => {
    try {
      const stored = await AsyncStorage.getItem('niv_auth');
      if (stored) {
        const parsed = JSON.parse(stored);
        // Verify token is still valid
        const res = await fetch(parsed.site_url + '/api/method/niv_ai.niv_core.api.mobile.verify_token', {
          method: 'POST',
          headers: {
            'Authorization': parsed.auth.token,
            'Content-Type': 'application/json',
          },
        });
        const data = await res.json();
        if (data.message && data.message.valid) {
          setAuth(parsed.auth);
          setConfig(parsed.config);
          setUserInfo(data.message.user);
          setScreen('chat');
          return;
        }
      }
    } catch (e) {
      console.log('Auth check failed:', e);
    }
    setScreen('pair');
  };

  const onPaired = async (result) => {
    const stored = {
      site_url: result.site_url,
      auth: result.auth,
      config: result.config,
      user: result.user,
    };
    await AsyncStorage.setItem('niv_auth', JSON.stringify(stored));
    await AsyncStorage.setItem('niv_site_url', result.site_url);
    setAuth(result.auth);
    setConfig(result.config);
    setUserInfo(result.user);
    setScreen('chat');
  };

  const onLogout = async () => {
    await AsyncStorage.removeItem('niv_auth');
    await AsyncStorage.removeItem('niv_site_url');
    setAuth(null);
    setConfig(null);
    setUserInfo(null);
    setScreen('pair');
  };

  if (screen === 'loading') return <LoadingScreen />;
  if (screen === 'pair') return <PairingScreen onPaired={onPaired} />;
  return <ChatScreen auth={auth} config={config} userInfo={userInfo} onLogout={onLogout} />;
}

// ══════════════════════════════════════════
// LOADING SCREEN
// ══════════════════════════════════════════
function LoadingScreen() {
  return (
    <View style={[styles.container, styles.center]}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      <Text style={styles.logo}>Niv AI</Text>
      <ActivityIndicator size="large" color={COLORS.purple} style={{ marginTop: 20 }} />
    </View>
  );
}

// ══════════════════════════════════════════
// PAIRING SCREEN
// ══════════════════════════════════════════
function PairingScreen({ onPaired }) {
  const [code, setCode] = useState('');
  const [siteUrl, setSiteUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState(1); // 1=url, 2=code

  useEffect(() => {
    AsyncStorage.getItem('niv_site_url').then(url => {
      if (url) setSiteUrl(url);
    });
  }, []);

  const handlePair = async () => {
    if (!siteUrl.trim()) {
      setError('Server URL is required');
      return;
    }
    if (!code.trim()) {
      setError('Pairing code is required');
      return;
    }

    setLoading(true);
    setError('');

    try {
      let url = siteUrl.trim().replace(/\/$/, '');
      const res = await fetch(url + '/api/method/niv_ai.niv_core.api.mobile.pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code.trim().toUpperCase(),
          device_name: Platform.OS + ' ' + (Platform.Version || ''),
        }),
      });

      const data = await res.json();

      if (data.message && data.message.success) {
        onPaired({ ...data.message, site_url: url });
      } else if (data.exc_type) {
        setError(data._server_messages ?
          JSON.parse(JSON.parse(data._server_messages)[0]).message :
          'Invalid pairing code');
      } else {
        setError('Pairing failed. Check your code and try again.');
      }
    } catch (e) {
      setError('Connection failed. Check your server URL.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.pairContainer}>
        <View style={styles.pairContent}>
          {/* Logo */}
          <View style={styles.pairLogo}>
            <Text style={styles.logo}>Niv AI</Text>
            <Text style={styles.pairSubtitle}>AI Assistant for ERPNext</Text>
          </View>

          {/* Step 1: Server URL */}
          <Text style={styles.inputLabel}>Server URL</Text>
          <TextInput
            style={styles.input}
            value={siteUrl}
            onChangeText={setSiteUrl}
            placeholder="https://erp.yourcompany.com"
            placeholderTextColor={COLORS.textMuted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
          <Text style={styles.inputHint}>Your ERPNext server address</Text>

          {/* Step 2: Pairing Code */}
          <Text style={[styles.inputLabel, { marginTop: 24 }]}>Pairing Code</Text>
          <TextInput
            style={[styles.input, styles.codeInput]}
            value={code}
            onChangeText={(t) => setCode(t.toUpperCase())}
            placeholder="NV-XXXXXXXX"
            placeholderTextColor={COLORS.textMuted}
            autoCapitalize="characters"
            maxLength={10}
            textAlign="center"
          />
          <Text style={styles.inputHint}>Get this from your admin</Text>

          {/* Error */}
          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          {/* Connect Button */}
          <TouchableOpacity
            style={[styles.pairButton, loading && styles.pairButtonDisabled]}
            onPress={handlePair}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.pairButtonText}>Connect</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ══════════════════════════════════════════
// CHAT SCREEN
// ══════════════════════════════════════════
function ChatScreen({ auth, config, userInfo, onLogout }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [currentTools, setCurrentTools] = useState([]);
  const flatListRef = useRef(null);
  const [siteUrl, setSiteUrl] = useState('');

  useEffect(() => {
    AsyncStorage.getItem('niv_site_url').then(url => {
      if (url) setSiteUrl(url);
    });
  }, []);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    Keyboard.dismiss();
    setInput('');
    setCurrentTools([]);

    // Add user message
    const userMsg = { id: Date.now(), role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);
    setStreaming(true);

    // Add placeholder for AI response
    const aiMsgId = Date.now() + 1;
    setMessages(prev => [...prev, { id: aiMsgId, role: 'assistant', content: '', tools: [] }]);

    try {
      const url = siteUrl + '/api/method/niv_ai.niv_core.api.stream.stream_chat';
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': auth.token,
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({ message: text }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';
      let tools = [];
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.substring(6).trim();
          if (!jsonStr || jsonStr === '[DONE]') continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === 'token' && event.content) {
              fullContent += event.content;
              setMessages(prev => prev.map(m =>
                m.id === aiMsgId ? { ...m, content: fullContent } : m
              ));
            } else if (event.type === 'tool_call') {
              tools.push(event.tool);
              setCurrentTools([...tools]);
              setMessages(prev => prev.map(m =>
                m.id === aiMsgId ? { ...m, tools: [...tools] } : m
              ));
            } else if (event.type === 'error') {
              fullContent += '\n⚠️ ' + (event.content || 'Error occurred');
              setMessages(prev => prev.map(m =>
                m.id === aiMsgId ? { ...m, content: fullContent } : m
              ));
            }
          } catch (e) {
            // Skip unparseable lines
          }
        }
      }

      // If no content received, show error
      if (!fullContent) {
        setMessages(prev => prev.map(m =>
          m.id === aiMsgId ? { ...m, content: '🤔 No response received.' } : m
        ));
      }

    } catch (e) {
      setMessages(prev => prev.map(m =>
        m.id === aiMsgId ? { ...m, content: '⚠️ Connection error: ' + e.message } : m
      ));
    } finally {
      setLoading(false);
      setStreaming(false);
      setCurrentTools([]);
    }
  };

  const renderMessage = ({ item }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.messageBubble, isUser ? styles.userBubble : styles.aiBubble]}>
        {/* Tool calls */}
        {item.tools && item.tools.length > 0 && (
          <View style={styles.toolsContainer}>
            {item.tools.map((tool, i) => (
              <View key={i} style={styles.toolChip}>
                <Text style={styles.toolChipText}>🔧 {tool}</Text>
              </View>
            ))}
          </View>
        )}
        {/* Message content */}
        <Text style={[styles.messageText, isUser && styles.userMessageText]}>
          {item.content || (streaming && !isUser ? '⏳ Thinking...' : '')}
        </Text>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>{config?.widget_title || 'Niv AI'}</Text>
          <Text style={styles.headerSubtitle}>{userInfo?.full_name || ''}</Text>
        </View>
        <TouchableOpacity onPress={() => {
          Alert.alert('Logout', 'Disconnect from server?', [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Logout', style: 'destructive', onPress: onLogout },
          ]);
        }}>
          <Text style={styles.logoutBtn}>⚙️</Text>
        </TouchableOpacity>
      </View>

      {/* Tool call indicator */}
      {currentTools.length > 0 && (
        <View style={styles.toolBar}>
          <Text style={styles.toolBarText}>
            🔧 {currentTools[currentTools.length - 1]}...
          </Text>
        </View>
      )}

      {/* Messages */}
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={item => String(item.id)}
        renderItem={renderMessage}
        contentContainerStyle={styles.messageList}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
        ListEmptyComponent={
          <View style={styles.emptyChat}>
            <Text style={styles.emptyChatIcon}>🤖</Text>
            <Text style={styles.emptyChatTitle}>Niv AI</Text>
            <Text style={styles.emptyChatText}>Ask me anything about your ERPNext data!</Text>
            <View style={styles.suggestionContainer}>
              {['Aaj ki sales kitni?', 'Pending invoices dikhao', 'Top 5 customers'].map((s, i) => (
                <TouchableOpacity key={i} style={styles.suggestion} onPress={() => { setInput(s); }}>
                  <Text style={styles.suggestionText}>{s}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        }
      />

      {/* Input */}
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.inputContainer}>
          <TextInput
            style={styles.chatInput}
            value={input}
            onChangeText={setInput}
            placeholder="Type a message..."
            placeholderTextColor={COLORS.textMuted}
            multiline
            maxLength={2000}
            returnKeyType="send"
            onSubmitEditing={sendMessage}
          />
          <TouchableOpacity
            style={[styles.sendButton, (!input.trim() || loading) && styles.sendButtonDisabled]}
            onPress={sendMessage}
            disabled={!input.trim() || loading}
          >
            {loading ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.sendButtonText}>➤</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ══════════════════════════════════════════
// STYLES
// ══════════════════════════════════════════
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  center: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  logo: {
    fontSize: 42,
    fontWeight: '800',
    color: COLORS.purple,
    letterSpacing: 2,
  },

  // ── Pairing ──
  pairContainer: {
    flex: 1,
    justifyContent: 'center',
  },
  pairContent: {
    paddingHorizontal: 32,
  },
  pairLogo: {
    alignItems: 'center',
    marginBottom: 48,
  },
  pairSubtitle: {
    fontSize: 14,
    color: COLORS.textDim,
    marginTop: 8,
  },
  inputLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.textDim,
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  input: {
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: COLORS.text,
  },
  codeInput: {
    fontSize: 24,
    fontWeight: '700',
    letterSpacing: 4,
    paddingVertical: 16,
  },
  inputHint: {
    fontSize: 11,
    color: COLORS.textMuted,
    marginTop: 6,
  },
  errorText: {
    color: COLORS.error,
    fontSize: 13,
    marginTop: 16,
    textAlign: 'center',
  },
  pairButton: {
    backgroundColor: COLORS.purple,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 32,
  },
  pairButtonDisabled: {
    opacity: 0.6,
  },
  pairButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },

  // ── Header ──
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text,
  },
  headerSubtitle: {
    fontSize: 12,
    color: COLORS.textDim,
    marginTop: 2,
  },
  logoutBtn: {
    fontSize: 24,
  },

  // ── Tool Bar ──
  toolBar: {
    backgroundColor: COLORS.surface,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  toolBarText: {
    color: COLORS.teal,
    fontSize: 12,
    fontWeight: '500',
  },

  // ── Messages ──
  messageList: {
    padding: 16,
    paddingBottom: 8,
  },
  messageBubble: {
    maxWidth: '85%',
    borderRadius: 16,
    padding: 12,
    marginBottom: 12,
  },
  userBubble: {
    backgroundColor: COLORS.purple,
    alignSelf: 'flex-end',
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    backgroundColor: COLORS.surface,
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  messageText: {
    color: COLORS.text,
    fontSize: 15,
    lineHeight: 22,
  },
  userMessageText: {
    color: '#fff',
  },
  toolsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 8,
  },
  toolChip: {
    backgroundColor: 'rgba(6, 182, 212, 0.15)',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    marginRight: 6,
    marginBottom: 4,
  },
  toolChipText: {
    color: COLORS.teal,
    fontSize: 11,
    fontWeight: '500',
  },

  // ── Empty Chat ──
  emptyChat: {
    alignItems: 'center',
    paddingTop: 80,
  },
  emptyChatIcon: {
    fontSize: 64,
    marginBottom: 16,
  },
  emptyChatTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: COLORS.purple,
    marginBottom: 8,
  },
  emptyChatText: {
    fontSize: 14,
    color: COLORS.textDim,
    marginBottom: 32,
  },
  suggestionContainer: {
    width: '100%',
    paddingHorizontal: 16,
  },
  suggestion: {
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 8,
  },
  suggestionText: {
    color: COLORS.textDim,
    fontSize: 14,
  },

  // ── Input ──
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    backgroundColor: COLORS.bg,
  },
  chatInput: {
    flex: 1,
    backgroundColor: COLORS.surface,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: COLORS.text,
    maxHeight: 100,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  sendButton: {
    backgroundColor: COLORS.purple,
    width: 44,
    height: 44,
    borderRadius: 22,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 8,
  },
  sendButtonDisabled: {
    opacity: 0.4,
  },
  sendButtonText: {
    color: '#fff',
    fontSize: 20,
  },
});
