import React, { useState, useEffect, useRef, useCallback, createContext, useContext } from 'react';
import {
  StyleSheet, View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, StatusBar, ActivityIndicator,
  SafeAreaView, Alert, Animated, Keyboard, Dimensions, Image,
  Easing, Modal, ScrollView, Linking, Pressable, Share, Switch,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import * as Speech from 'expo-speech';
import * as LocalAuthentication from 'expo-local-authentication';
import Markdown from 'react-native-markdown-display';
import { DARK, LIGHT } from './src/theme';
import { NivAPI } from './src/api';

const { width: SW, height: SH } = Dimensions.get('window');
const ThemeCtx = createContext(DARK);
const useTheme = () => useContext(ThemeCtx);

// ════════════════════════════════════════════════
// APP ROOT — Theme + Auth + Biometric
// ════════════════════════════════════════════════
export default function App() {
  const [screen, setScreen] = useState('loading');
  const [session, setSession] = useState(null);
  const [theme, setTheme] = useState('dark');
  const [biometricEnabled, setBiometricEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  const T = theme === 'dark' ? DARK : LIGHT;

  useEffect(() => { init(); }, []);

  const init = async () => {
    // Load theme preference
    const savedTheme = await AsyncStorage.getItem('niv_theme');
    if (savedTheme) setTheme(savedTheme);

    // Check biometric
    const bioEnabled = await AsyncStorage.getItem('niv_biometric');
    if (bioEnabled === 'true') {
      setBiometricEnabled(true);
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Unlock Niv AI',
        cancelLabel: 'Cancel',
        disableDeviceFallback: false,
      });
      if (!result.success) {
        Alert.alert('Authentication Failed', 'Please try again.');
        return;
      }
    }
    setAuthenticated(true);

    // Load session
    try {
      const raw = await AsyncStorage.getItem('niv_session');
      if (raw) {
        const s = JSON.parse(raw);
        const res = await fetch(s.siteUrl + '/api/method/niv_ai.niv_core.api.mobile.verify_token', {
          method: 'POST',
          headers: { 'Authorization': s.token, 'Content-Type': 'application/json' },
        });
        if (res.ok) {
          const d = await res.json();
          if (d.message?.valid) {
            setSession({ ...s, companies: d.message.companies || s.companies });
            setScreen('chat');
            return;
          }
        }
      }
    } catch (e) {}
    setScreen('pair');
  };

  const onPaired = async (data) => {
    await AsyncStorage.setItem('niv_session', JSON.stringify(data));
    setSession(data);
    setScreen('welcome');
    setTimeout(() => setScreen('chat'), 2800);
  };

  const onLogout = async () => {
    await AsyncStorage.removeItem('niv_session');
    await AsyncStorage.removeItem('niv_conversations');
    setSession(null);
    setScreen('pair');
  };

  const toggleTheme = async () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    await AsyncStorage.setItem('niv_theme', next);
  };

  const toggleBiometric = async (val) => {
    if (val) {
      const compatible = await LocalAuthentication.hasHardwareAsync();
      if (!compatible) { Alert.alert('Not Available', 'Biometric auth not supported on this device.'); return; }
      const enrolled = await LocalAuthentication.isEnrolledAsync();
      if (!enrolled) { Alert.alert('Not Set Up', 'Please set up fingerprint or face unlock first.'); return; }
    }
    setBiometricEnabled(val);
    await AsyncStorage.setItem('niv_biometric', val.toString());
  };

  if (!authenticated) {
    return <View style={[st.fill, st.center, { backgroundColor: DARK.bg }]}><StatusBar barStyle="light-content" /><ActivityIndicator color={DARK.accent} size="large" /></View>;
  }

  return (
    <ThemeCtx.Provider value={T}>
      {screen === 'loading' && <LoadingScreen />}
      {screen === 'pair' && <PairScreen onPaired={onPaired} />}
      {screen === 'welcome' && <WelcomeScreen session={session} />}
      {screen === 'chat' && (
        <ChatScreen
          session={session}
          onLogout={onLogout}
          theme={theme}
          toggleTheme={toggleTheme}
          biometricEnabled={biometricEnabled}
          toggleBiometric={toggleBiometric}
        />
      )}
    </ThemeCtx.Provider>
  );
}

// ════════════════════════════════════════════════
// LOADING
// ════════════════════════════════════════════════
function LoadingScreen() {
  const T = useTheme();
  const pulse = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 800, useNativeDriver: true }),
      Animated.timing(pulse, { toValue: 0.3, duration: 800, useNativeDriver: true }),
    ])).start();
  }, []);
  return (
    <View style={[st.fill, st.center, { backgroundColor: T.bg }]}>
      <StatusBar barStyle={T.bg === '#000000' ? 'light-content' : 'dark-content'} backgroundColor={T.bg} />
      <Animated.Text style={{ fontSize: 64, fontWeight: '800', color: T.accent, opacity: pulse }}>N</Animated.Text>
    </View>
  );
}

// ════════════════════════════════════════════════
// PAIR SCREEN
// ════════════════════════════════════════════════
function PairScreen({ onPaired }) {
  const T = useTheme();
  const [step, setStep] = useState(1);
  const [url, setUrl] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fade = useRef(new Animated.Value(0)).current;
  const slide = useRef(new Animated.Value(30)).current;

  useEffect(() => {
    fade.setValue(0); slide.setValue(30);
    Animated.parallel([
      Animated.timing(fade, { toValue: 1, duration: 500, useNativeDriver: true }),
      Animated.timing(slide, { toValue: 0, duration: 500, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
    ]).start();
  }, [step]);

  const goNext = () => {
    if (!url.trim()) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setError(''); setStep(2);
  };

  const connect = async () => {
    if (!code.trim()) return;
    setLoading(true); setError('');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    let base = url.trim().replace(/\/+$/, '');
    if (!base.startsWith('http')) base = 'https://' + base;
    try {
      const res = await fetch(base + '/api/method/niv_ai.niv_core.api.mobile.pair', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim().toUpperCase(), device_name: Platform.OS }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msgs = data._server_messages ? JSON.parse(data._server_messages) : [];
        throw new Error(msgs.length ? JSON.parse(msgs[0]).message : 'Connection failed');
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      const m = data.message;
      onPaired({ siteUrl: base, token: m.auth.token, user: m.user, companies: m.companies || [], config: m.config });
    } catch (e) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setError(e.message || 'Failed');
    } finally { setLoading(false); }
  };

  // Multi-server support
  const [servers, setServers] = useState([]);
  useEffect(() => {
    AsyncStorage.getItem('niv_servers').then(raw => {
      if (raw) setServers(JSON.parse(raw));
    });
  }, []);

  const saveServer = async (serverUrl) => {
    const updated = [...new Set([serverUrl, ...servers])].slice(0, 5);
    setServers(updated);
    await AsyncStorage.setItem('niv_servers', JSON.stringify(updated));
  };

  return (
    <SafeAreaView style={[st.fill, { backgroundColor: T.bg }]}>
      <StatusBar barStyle={T.bg === '#000000' ? 'light-content' : 'dark-content'} backgroundColor={T.bg} />
      <KeyboardAvoidingView style={st.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={{ flex: 1, justifyContent: 'center', paddingHorizontal: 32 }}>
          <View style={{ alignItems: 'center', marginBottom: 56 }}>
            <View style={[st.nCircle, { backgroundColor: T.surface, borderColor: T.accentMid }]}>
              <Text style={[st.nLogo, { color: T.accent }]}>N</Text>
            </View>
          </View>

          <Animated.View style={{ opacity: fade, transform: [{ translateY: slide }] }}>
            {step === 1 ? (
              <>
                <Text style={[st.fieldLabel, { color: T.t3 }]}>SERVER</Text>
                <TextInput
                  style={[st.fieldInput, { backgroundColor: T.surface, color: T.t1, borderColor: T.t4 }]}
                  value={url} onChangeText={setUrl}
                  placeholder="your-company.com" placeholderTextColor={T.t4}
                  autoCapitalize="none" autoCorrect={false} keyboardType="url"
                  returnKeyType="next" onSubmitEditing={goNext}
                />
                {/* Recent servers */}
                {servers.length > 0 && (
                  <View style={{ marginTop: 12 }}>
                    <Text style={{ color: T.t3, fontSize: 11, marginBottom: 6 }}>RECENT</Text>
                    {servers.map((s, i) => (
                      <TouchableOpacity key={i} onPress={() => { setUrl(s); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
                        style={{ paddingVertical: 8, paddingHorizontal: 12, backgroundColor: T.card, borderRadius: 10, marginBottom: 4 }}>
                        <Text style={{ color: T.t2, fontSize: 13 }}>{s}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
                <TouchableOpacity style={[st.mainBtn, { backgroundColor: T.accent }]} onPress={goNext} activeOpacity={0.8}>
                  <Text style={st.mainBtnT}>Continue</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                <Text style={[st.fieldLabel, { color: T.t3 }]}>PAIRING CODE</Text>
                <TextInput
                  style={[st.fieldInput, { backgroundColor: T.surface, color: T.t1, borderColor: T.t4, fontSize: 28, fontWeight: '800', letterSpacing: 8, textAlign: 'center' }]}
                  value={code} onChangeText={t => setCode(t.toUpperCase())}
                  placeholder="• • • • • • • •" placeholderTextColor={T.t4}
                  autoCapitalize="characters" maxLength={8} autoFocus
                />
                {error ? <Text style={{ color: T.red, fontSize: 13, textAlign: 'center', marginTop: 14 }}>{error}</Text> : null}
                <TouchableOpacity style={[st.mainBtn, { backgroundColor: T.accent }, loading && { opacity: 0.5 }]}
                  onPress={() => { saveServer(url.trim()); connect(); }} disabled={loading} activeOpacity={0.8}>
                  {loading ? <ActivityIndicator color="#fff" /> : <Text style={st.mainBtnT}>Connect</Text>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { setStep(1); setError(''); }} style={{ marginTop: 20 }}>
                  <Text style={{ color: T.t3, textAlign: 'center' }}>← Back</Text>
                </TouchableOpacity>
              </>
            )}
          </Animated.View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ════════════════════════════════════════════════
// WELCOME — Handshake
// ════════════════════════════════════════════════
function WelcomeScreen({ session }) {
  const T = useTheme();
  const s1 = useRef(new Animated.Value(0)).current;
  const s2 = useRef(new Animated.Value(0)).current;
  const line = useRef(new Animated.Value(0)).current;
  const txt = useRef(new Animated.Value(0)).current;
  const co = session?.companies?.[0];

  useEffect(() => {
    Animated.sequence([
      Animated.spring(s1, { toValue: 1, friction: 5, useNativeDriver: true }),
      Animated.spring(s2, { toValue: 1, friction: 5, useNativeDriver: true }),
      Animated.timing(line, { toValue: 1, duration: 350, useNativeDriver: true }),
      Animated.timing(txt, { toValue: 1, duration: 400, useNativeDriver: true }),
    ]).start();
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  }, []);

  return (
    <View style={[st.fill, st.center, { backgroundColor: T.bg }]}>
      <StatusBar barStyle="light-content" backgroundColor={T.bg} />
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Animated.View style={[st.wCircle, { backgroundColor: T.surface, borderColor: T.accentMid }, { transform: [{ scale: s1 }] }]}>
          <Text style={{ fontSize: 36, fontWeight: '800', color: T.accent }}>N</Text>
        </Animated.View>
        <Animated.View style={{ opacity: line, marginHorizontal: 14 }}>
          <Text style={{ fontSize: 28 }}>🤝</Text>
        </Animated.View>
        <Animated.View style={[st.wCircle, { backgroundColor: T.surface, borderColor: T.greenDim }, { transform: [{ scale: s2 }] }]}>
          {co?.logo ? (
            <Image source={{ uri: co.logo }} style={{ width: 44, height: 44, borderRadius: 8 }} resizeMode="contain" />
          ) : (
            <Text style={{ fontSize: 22, fontWeight: '700', color: T.t1 }}>{co?.abbr || '🏢'}</Text>
          )}
        </Animated.View>
      </View>
      <Animated.View style={{ opacity: txt, marginTop: 36, alignItems: 'center' }}>
        <Text style={{ fontSize: 26, fontWeight: '700', color: T.green }}>Connected</Text>
        <Text style={{ fontSize: 17, color: T.t1, marginTop: 8, fontWeight: '600' }}>{co?.company_name || ''}</Text>
        <Text style={{ fontSize: 13, color: T.t3, marginTop: 4 }}>{session?.user?.full_name}</Text>
      </Animated.View>
    </View>
  );
}

// ════════════════════════════════════════════════
// SETTINGS MODAL — Phase 7 & 8
// ════════════════════════════════════════════════
function SettingsModal({ visible, onClose, session, theme, toggleTheme, biometricEnabled, toggleBiometric, onLogout }) {
  const T = useTheme();
  const [devMode, setDevMode] = useState(false);
  const [errorLogs, setErrorLogs] = useState([]);
  const [showErrors, setShowErrors] = useState(false);
  const [lang, setLang] = useState('en');

  useEffect(() => {
    AsyncStorage.getItem('niv_lang').then(v => { if (v) setLang(v); });
    AsyncStorage.getItem('niv_devmode').then(v => { if (v === 'true') setDevMode(true); });
  }, []);

  const toggleDev = async (val) => {
    setDevMode(val);
    await AsyncStorage.setItem('niv_devmode', val.toString());
    if (val) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  };

  const fetchErrors = async () => {
    if (!session) return;
    try {
      const api = new NivAPI(session.siteUrl, session.token);
      const logs = await api.getErrorLogs(15);
      setErrorLogs(logs || []);
      setShowErrors(true);
    } catch (e) {
      Alert.alert('Error', e.message);
    }
  };

  const toggleLang = async () => {
    const next = lang === 'en' ? 'hi' : 'en';
    setLang(next);
    await AsyncStorage.setItem('niv_lang', next);
  };

  const co = session?.companies?.[0];

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)' }}>
        <View style={{ flex: 1, marginTop: 60, backgroundColor: T.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24, overflow: 'hidden' }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, borderBottomWidth: 1, borderColor: T.border }}>
            <Text style={{ fontSize: 22, fontWeight: '700', color: T.t1 }}>Settings</Text>
            <TouchableOpacity onPress={onClose}><Text style={{ color: T.accent, fontSize: 16, fontWeight: '600' }}>Done</Text></TouchableOpacity>
          </View>

          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 40 }}>
            {/* Profile */}
            <View style={{ alignItems: 'center', paddingVertical: 24 }}>
              <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: T.accentDim, justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: T.accentMid }}>
                <Text style={{ fontSize: 28, fontWeight: '800', color: T.accent }}>{(session?.user?.full_name?.[0] || 'U').toUpperCase()}</Text>
              </View>
              <Text style={{ fontSize: 18, fontWeight: '600', color: T.t1, marginTop: 10 }}>{session?.user?.full_name}</Text>
              <Text style={{ fontSize: 13, color: T.t3 }}>{session?.user?.email}</Text>
              {co && <Text style={{ fontSize: 12, color: T.t3, marginTop: 2 }}>{co.company_name}</Text>}
            </View>

            {/* Appearance */}
            <SettSection title="APPEARANCE" T={T}>
              <SettRow icon="🌙" label="Dark Mode" T={T} right={
                <Switch value={theme === 'dark'} onValueChange={toggleTheme} trackColor={{ false: T.t4, true: T.accent }} thumbColor="#fff" />
              } />
              <SettRow icon="🌐" label={`Language: ${lang === 'en' ? 'English' : 'हिंदी'}`} T={T} onPress={toggleLang} />
            </SettSection>

            {/* Security */}
            <SettSection title="SECURITY" T={T}>
              <SettRow icon="🔐" label="Biometric Lock" T={T} right={
                <Switch value={biometricEnabled} onValueChange={toggleBiometric} trackColor={{ false: T.t4, true: T.accent }} thumbColor="#fff" />
              } />
            </SettSection>

            {/* Developer */}
            <SettSection title="DEVELOPER" T={T}>
              <SettRow icon="🛠️" label="Developer Mode" T={T} right={
                <Switch value={devMode} onValueChange={toggleDev} trackColor={{ false: T.t4, true: T.orange }} thumbColor="#fff" />
              } />
              {devMode && (
                <>
                  <SettRow icon="🐛" label="Error Logs" T={T} onPress={fetchErrors} />
                  <SettRow icon="📊" label="System Info" T={T} onPress={() => {
                    Alert.alert('System', `Server: ${session?.siteUrl}\nUser: ${session?.user?.email}\nCompanies: ${session?.companies?.length || 0}`);
                  }} />
                </>
              )}
            </SettSection>

            {/* Connection */}
            <SettSection title="CONNECTION" T={T}>
              <SettRow icon="🔗" label={session?.siteUrl || 'Not connected'} T={T} sub />
              <SettRow icon="🚪" label="Logout" T={T} danger onPress={() => {
                Alert.alert('Logout?', 'Disconnect and clear data?', [
                  { text: 'Cancel' },
                  { text: 'Logout', style: 'destructive', onPress: () => { onClose(); onLogout(); } },
                ]);
              }} />
            </SettSection>

            {/* Version */}
            <Text style={{ textAlign: 'center', color: T.t4, fontSize: 12, marginTop: 20 }}>Niv AI v1.0.0</Text>
          </ScrollView>

          {/* Error Logs Modal */}
          <Modal visible={showErrors} animationType="slide" transparent>
            <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', paddingTop: 100 }}>
              <View style={{ flex: 1, backgroundColor: T.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderColor: T.border }}>
                  <Text style={{ fontSize: 18, fontWeight: '700', color: T.t1 }}>🐛 Error Logs</Text>
                  <TouchableOpacity onPress={() => setShowErrors(false)}><Text style={{ color: T.accent, fontWeight: '600' }}>Close</Text></TouchableOpacity>
                </View>
                <ScrollView style={{ padding: 12 }}>
                  {errorLogs.map((log, i) => (
                    <View key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: T.border }}>
                      <Text style={{ color: T.red, fontSize: 12, fontWeight: '600' }}>{log.method}</Text>
                      <Text style={{ color: T.t2, fontSize: 11, marginTop: 4 }} numberOfLines={3}>{log.error}</Text>
                      <Text style={{ color: T.t4, fontSize: 10, marginTop: 4 }}>{log.creation}</Text>
                    </View>
                  ))}
                  {errorLogs.length === 0 && <Text style={{ color: T.t3, textAlign: 'center', marginTop: 40 }}>No errors 🎉</Text>}
                </ScrollView>
              </View>
            </View>
          </Modal>
        </View>
      </View>
    </Modal>
  );
}

// Settings helpers
function SettSection({ title, T, children }) {
  return (
    <View style={{ marginTop: 24 }}>
      <Text style={{ fontSize: 12, fontWeight: '700', color: T.t3, paddingHorizontal: 20, marginBottom: 8, letterSpacing: 1.5 }}>{title}</Text>
      <View style={{ marginHorizontal: 16, backgroundColor: T.surface, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }}>
        {children}
      </View>
    </View>
  );
}

function SettRow({ icon, label, T, right, onPress, danger, sub }) {
  const content = (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
        <Text style={{ fontSize: 18, marginRight: 12 }}>{icon}</Text>
        <Text style={{ fontSize: 15, color: danger ? T.red : (sub ? T.t3 : T.t1), fontWeight: danger ? '600' : '400' }} numberOfLines={1}>{label}</Text>
      </View>
      {right || (onPress && <Text style={{ color: T.t3, fontSize: 16 }}>›</Text>)}
    </View>
  );
  if (onPress) return <TouchableOpacity onPress={onPress} activeOpacity={0.7}>{content}</TouchableOpacity>;
  return content;
}

// ════════════════════════════════════════════════
// QUICK ACTIONS MODAL — Phase 6
// ════════════════════════════════════════════════
function QuickActionsModal({ visible, onClose, session }) {
  const T = useTheme();
  const [actionType, setActionType] = useState(null);
  const [formData, setFormData] = useState({});
  const [creating, setCreating] = useState(false);

  const actions = [
    { icon: '👤', label: 'New Customer', doctype: 'Customer', fields: [
      { key: 'customer_name', label: 'Customer Name', required: true },
      { key: 'customer_type', label: 'Type', default: 'Individual' },
      { key: 'mobile_no', label: 'Mobile', keyboard: 'phone-pad' },
    ]},
    { icon: '📄', label: 'Sales Order', doctype: 'Sales Order', fields: [
      { key: 'customer', label: 'Customer', required: true },
      { key: 'delivery_date', label: 'Delivery Date' },
    ]},
    { icon: '🧾', label: 'Sales Invoice', doctype: 'Sales Invoice', fields: [
      { key: 'customer', label: 'Customer', required: true },
    ]},
    { icon: '📝', label: 'ToDo', doctype: 'ToDo', fields: [
      { key: 'description', label: 'Description', required: true, multiline: true },
      { key: 'priority', label: 'Priority', default: 'Medium' },
    ]},
    { icon: '📌', label: 'Note', doctype: 'Note', fields: [
      { key: 'title', label: 'Title', required: true },
      { key: 'content', label: 'Content', multiline: true },
    ]},
  ];

  const create = async () => {
    if (!session || !actionType) return;
    setCreating(true);
    try {
      const api = new NivAPI(session.siteUrl, session.token);
      const values = { ...formData };
      for (const f of actionType.fields) {
        if (!values[f.key] && f.default) values[f.key] = f.default;
      }
      await api.createDoc(actionType.doctype, values);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      Alert.alert('Created! ✅', `${actionType.doctype} created successfully.`);
      setFormData({});
      setActionType(null);
      onClose();
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)' }}>
        <Pressable style={{ flex: 0.3 }} onPress={() => { setActionType(null); onClose(); }} />
        <View style={{ flex: 0.7, backgroundColor: T.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: 20 }}>
            <Text style={{ fontSize: 20, fontWeight: '700', color: T.t1 }}>
              {actionType ? '📝 ' + actionType.label : '⚡ Quick Actions'}
            </Text>
            <TouchableOpacity onPress={() => { setActionType(null); onClose(); }}>
              <Text style={{ color: T.accent, fontWeight: '600' }}>Close</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={{ padding: 16 }}>
            {!actionType ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                {actions.map((a, i) => (
                  <TouchableOpacity key={i} onPress={() => { setActionType(a); setFormData({}); }}
                    style={{ width: (SW - 56) / 2, backgroundColor: T.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}
                    activeOpacity={0.7}>
                    <Text style={{ fontSize: 32, marginBottom: 8 }}>{a.icon}</Text>
                    <Text style={{ color: T.t1, fontSize: 14, fontWeight: '600' }}>{a.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : (
              <>
                {actionType.fields.map((f, i) => (
                  <View key={i} style={{ marginBottom: 16 }}>
                    <Text style={{ color: T.t3, fontSize: 12, fontWeight: '600', marginBottom: 6, letterSpacing: 1 }}>
                      {f.label.toUpperCase()}{f.required ? ' *' : ''}
                    </Text>
                    <TextInput
                      style={{ backgroundColor: T.surface, borderRadius: 12, paddingHorizontal: 16, paddingVertical: 12, fontSize: 15, color: T.t1, borderWidth: 1, borderColor: T.t4, ...(f.multiline ? { height: 80, textAlignVertical: 'top' } : {}) }}
                      value={formData[f.key] || ''}
                      onChangeText={v => setFormData(p => ({ ...p, [f.key]: v }))}
                      placeholder={f.default || f.label}
                      placeholderTextColor={T.t4}
                      multiline={f.multiline}
                      keyboardType={f.keyboard || 'default'}
                    />
                  </View>
                ))}
                <TouchableOpacity
                  style={[st.mainBtn, { backgroundColor: T.accent, marginTop: 8 }, creating && { opacity: 0.5 }]}
                  onPress={create} disabled={creating} activeOpacity={0.8}>
                  {creating ? <ActivityIndicator color="#fff" /> : <Text style={st.mainBtnT}>Create {actionType.label}</Text>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setActionType(null)} style={{ marginTop: 16 }}>
                  <Text style={{ color: T.t3, textAlign: 'center' }}>← Back to actions</Text>
                </TouchableOpacity>
              </>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

// ════════════════════════════════════════════════
// CHAT SCREEN — All Features Combined
// ════════════════════════════════════════════════
function ChatScreen({ session, onLogout, theme, toggleTheme, biometricEnabled, toggleBiometric }) {
  const T = useTheme();

  // State
  const [convos, setConvos] = useState([]);
  const [activeConvo, setActiveConvo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [toolInfo, setToolInfo] = useState('');
  const [showScroll, setShowScroll] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [quickActionsOpen, setQuickActionsOpen] = useState(false);
  const [xhrRef, setXhrRef] = useState(null);

  const listRef = useRef(null);
  const drawerAnim = useRef(new Animated.Value(-SW * 0.82)).current;
  const co = session?.companies?.[0];
  const userName = session?.user?.full_name || 'User';
  const initial = userName[0]?.toUpperCase() || 'U';

  // Markdown styles based on theme
  const mdStyles = {
    body: { color: T.t1, fontSize: 15, lineHeight: 22 },
    heading1: { color: T.t1, fontSize: 22, fontWeight: '700', marginVertical: 8 },
    heading2: { color: T.t1, fontSize: 19, fontWeight: '700', marginVertical: 6 },
    heading3: { color: T.t1, fontSize: 17, fontWeight: '600', marginVertical: 4 },
    strong: { color: T.white, fontWeight: '700' },
    em: { color: T.t2, fontStyle: 'italic' },
    link: { color: T.accent, textDecorationLine: 'underline' },
    blockquote: { backgroundColor: T.card, borderLeftColor: T.accent, borderLeftWidth: 3, paddingLeft: 12, paddingVertical: 6, marginVertical: 6 },
    code_inline: { backgroundColor: T.elevated, color: T.teal, fontSize: 13, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
    code_block: { backgroundColor: T.card, color: T.teal, fontSize: 13, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', padding: 14, borderRadius: 12, marginVertical: 8, borderWidth: 1, borderColor: T.border },
    fence: { backgroundColor: T.card, color: T.teal, fontSize: 13, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', padding: 14, borderRadius: 12, marginVertical: 8, borderWidth: 1, borderColor: T.border },
    table: { borderWidth: 1, borderColor: T.t4, borderRadius: 8, marginVertical: 8 },
    thead: { backgroundColor: T.elevated },
    th: { color: T.t1, fontWeight: '600', padding: 8 },
    td: { color: T.t2, padding: 8 },
    tr: { borderBottomWidth: 1, borderColor: T.t4 },
    hr: { backgroundColor: T.t4, height: 1, marginVertical: 12 },
    paragraph: { marginVertical: 3 },
    bullet_list: { marginVertical: 4 },
    ordered_list: { marginVertical: 4 },
  };

  // ── Conversations ──
  useEffect(() => { loadConvos(); }, []);

  const loadConvos = async () => {
    try {
      const raw = await AsyncStorage.getItem('niv_conversations');
      if (raw) {
        const list = JSON.parse(raw);
        setConvos(list);
        if (list.length > 0) { setActiveConvo(list[0].id); setMessages(list[0].messages || []); }
      }
    } catch (e) {}
  };

  const saveConvos = async (list) => {
    setConvos(list);
    await AsyncStorage.setItem('niv_conversations', JSON.stringify(list));
  };

  const newChat = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const id = Date.now().toString();
    const c = { id, title: 'New Chat', messages: [], pinned: false, created: new Date().toISOString() };
    saveConvos([c, ...convos]);
    setActiveConvo(id); setMessages([]);
    toggleDrawer(false);
  };

  const switchConvo = (c) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setActiveConvo(c.id); setMessages(c.messages || []);
    toggleDrawer(false);
  };

  const deleteConvo = (id) => {
    Alert.alert('Delete Chat?', '', [
      { text: 'Cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        const updated = convos.filter(c => c.id !== id);
        saveConvos(updated);
        if (activeConvo === id) {
          if (updated.length) { setActiveConvo(updated[0].id); setMessages(updated[0].messages || []); }
          else { setActiveConvo(null); setMessages([]); }
        }
      }},
    ]);
  };

  const pinConvo = (id) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const updated = convos.map(c => c.id === id ? { ...c, pinned: !c.pinned } : c);
    updated.sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));
    saveConvos(updated);
  };

  const toggleDrawer = (open) => {
    Animated.spring(drawerAnim, { toValue: open ? 0 : -SW * 0.82, friction: 10, useNativeDriver: true }).start();
    setDrawerOpen(open);
  };

  // Save messages
  useEffect(() => {
    if (!activeConvo || messages.length === 0) return;
    const title = messages.find(m => m.role === 'user')?.content?.substring(0, 40) || 'New Chat';
    let updated = convos.map(c => c.id === activeConvo ? { ...c, messages, title } : c);
    if (!updated.find(c => c.id === activeConvo)) {
      updated = [{ id: activeConvo, title, messages, pinned: false, created: new Date().toISOString() }, ...updated];
    }
    saveConvos(updated);
  }, [messages]);

  // ── Send ──
  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput(''); Keyboard.dismiss();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    if (!activeConvo) {
      const id = Date.now().toString();
      setActiveConvo(id);
    }

    const uid = Date.now();
    const aid = uid + 1;
    setMessages(p => [...p, { id: uid, role: 'user', content: text }, { id: aid, role: 'assistant', content: '', tools: [], reactions: {} }]);
    setLoading(true); setStreaming(true);

    try {
      const api = new NivAPI(session.siteUrl, session.token);
      let full = '';
      let tools = [];

      await new Promise((resolve, reject) => {
        const xhr = api.streamChat(text, {
          onToken: (t) => {
            full += t;
            setMessages(p => p.map(m => m.id === aid ? { ...m, content: full } : m));
          },
          onTool: (t) => {
            tools.push(t);
            setToolInfo(t);
            setMessages(p => p.map(m => m.id === aid ? { ...m, tools: [...tools] } : m));
          },
          onError: (e) => {
            full += '\n⚠️ ' + e;
            setMessages(p => p.map(m => m.id === aid ? { ...m, content: full } : m));
          },
          onDone: resolve,
        });
        xhr.onerror = () => reject(new Error('Network error'));
        setXhrRef(xhr);
      });

      if (!full) setMessages(p => p.map(m => m.id === aid ? { ...m, content: 'No response.' } : m));
    } catch (e) {
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: '⚠️ ' + e.message } : m));
    } finally {
      setLoading(false); setStreaming(false); setToolInfo(''); setXhrRef(null);
    }
  };

  // ── Stop streaming ──
  const stopStreaming = () => {
    if (xhrRef) { xhrRef.abort(); setXhrRef(null); }
    setLoading(false); setStreaming(false); setToolInfo('');
  };

  // ── Actions ──
  const speakText = (text) => {
    if (speaking) { Speech.stop(); setSpeaking(false); return; }
    setSpeaking(true);
    Speech.speak(text, { language: 'hi-IN', rate: 0.95, onDone: () => setSpeaking(false), onError: () => setSpeaking(false) });
  };

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7, base64: true });
    if (!result.canceled && result.assets?.[0]) {
      Alert.alert('📸 Coming Soon', 'Image analysis will be available in next update!');
    }
  };

  const takePhoto = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { Alert.alert('Permission needed', 'Camera access required.'); return; }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.7, base64: true });
    if (!result.canceled && result.assets?.[0]) {
      Alert.alert('📸 Coming Soon', 'Document scanning will be available in next update!');
    }
  };

  const copyMsg = (text) => {
    Clipboard.setStringAsync(text);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const react = (msgId, emoji) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setMessages(p => p.map(m => {
      if (m.id !== msgId) return m;
      const r = { ...(m.reactions || {}) };
      r[emoji] ? delete r[emoji] : r[emoji] = true;
      return { ...m, reactions: r };
    }));
  };

  const showMsgActions = (item) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const opts = [
      { text: '📋 Copy', onPress: () => copyMsg(item.content) },
      { text: '📤 Share', onPress: () => Share.share({ message: item.content }) },
    ];
    if (item.role === 'assistant') {
      opts.push({ text: '🔊 Speak', onPress: () => speakText(item.content) });
      opts.push({ text: '👍 Like', onPress: () => react(item.id, '👍') });
      opts.push({ text: '👎 Dislike', onPress: () => react(item.id, '👎') });
    }
    opts.push({ text: 'Cancel', style: 'cancel' });
    Alert.alert('', '', opts);
  };

  // ── Render Message ──
  const renderMsg = ({ item, index }) => {
    const isUser = item.role === 'user';
    const isTyping = !isUser && streaming && index === messages.length - 1 && !item.content;
    const hasReact = item.reactions && Object.keys(item.reactions).length > 0;

    return (
      <Pressable onLongPress={() => showMsgActions(item)} delayLongPress={350}>
        <View style={[{ flexDirection: 'row', marginBottom: 10, alignItems: 'flex-start' }, isUser && { justifyContent: 'flex-end' }]}>
          {!isUser && <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: T.accentDim, justifyContent: 'center', alignItems: 'center', marginRight: 8, marginTop: 4 }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: T.accent }}>N</Text>
          </View>}

          <View style={{ maxWidth: SW * 0.78, flexShrink: 1 }}>
            {item.tools?.length > 0 && (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: 6 }}>
                {item.tools.map((t, i) => (
                  <View key={i} style={{ backgroundColor: T.tealDim, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 4, marginRight: 6, marginBottom: 4, borderWidth: 1, borderColor: T.teal + '20' }}>
                    <Text style={{ fontSize: 11, color: T.teal, fontWeight: '600' }}>⚡ {t}</Text>
                  </View>
                ))}
              </View>
            )}

            {isTyping ? (
              <TypingIndicator T={T} />
            ) : isUser ? (
              <View style={{ backgroundColor: T.accent, borderRadius: 20, borderTopRightRadius: 6, paddingHorizontal: 16, paddingVertical: 12 }}>
                <Text style={{ fontSize: 15, lineHeight: 22, color: '#fff' }}>{item.content}</Text>
              </View>
            ) : (
              <View style={{ backgroundColor: T.card, borderRadius: 20, borderTopLeftRadius: 6, paddingHorizontal: 16, paddingVertical: 10, borderWidth: 1, borderColor: T.border }}>
                <Markdown style={mdStyles} onLinkPress={(url) => { Linking.openURL(url); return false; }}>
                  {item.content || ''}
                </Markdown>
              </View>
            )}

            {hasReact && (
              <View style={{ flexDirection: 'row', marginTop: 4, marginLeft: 4 }}>
                {Object.keys(item.reactions).map(e => (
                  <TouchableOpacity key={e} onPress={() => react(item.id, e)}
                    style={{ backgroundColor: T.elevated, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 2, marginRight: 4, borderWidth: 1, borderColor: T.t4 }}>
                    <Text style={{ fontSize: 14 }}>{e}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {!isUser && !isTyping && item.content && !streaming && (
              <View style={{ flexDirection: 'row', marginTop: 4, marginLeft: 2, gap: 2 }}>
                {['👍', '👎', '📋', '🔊'].map(e => (
                  <TouchableOpacity key={e} onPress={() => e === '📋' ? copyMsg(item.content) : e === '🔊' ? speakText(item.content) : react(item.id, e)} style={{ padding: 4 }}>
                    <Text style={{ fontSize: 13 }}>{e}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
          </View>

          {isUser && <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: T.elevated, justifyContent: 'center', alignItems: 'center', marginLeft: 8, marginTop: 4 }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: T.t2 }}>{initial}</Text>
          </View>}
        </View>
      </Pressable>
    );
  };

  const filteredConvos = searchQ ? convos.filter(c => c.title?.toLowerCase().includes(searchQ.toLowerCase())) : convos;

  const suggestions = [
    { icon: '📊', text: 'Aaj ki sales kitni hai?' },
    { icon: '📋', text: 'Pending invoices dikhao' },
    { icon: '👥', text: 'Top 5 customers kaun hain?' },
    { icon: '📦', text: 'Stock levels check karo' },
  ];

  return (
    <SafeAreaView style={[st.fill, { backgroundColor: T.bg }]}>
      <StatusBar barStyle={T.bg === '#000000' ? 'light-content' : 'dark-content'} backgroundColor={T.bg} />

      {/* Drawer overlay */}
      {drawerOpen && <Pressable style={{ ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 10 }} onPress={() => toggleDrawer(false)} />}

      {/* ══ Drawer ══ */}
      <Animated.View style={{
        position: 'absolute', top: 0, bottom: 0, left: 0, width: SW * 0.82,
        backgroundColor: T.surface, zIndex: 20,
        paddingTop: Platform.OS === 'ios' ? 56 : (StatusBar.currentHeight || 0) + 10,
        borderRightWidth: 1, borderColor: T.border,
        transform: [{ translateX: drawerAnim }],
      }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingBottom: 14 }}>
          <Text style={{ fontSize: 22, fontWeight: '700', color: T.t1 }}>Chats</Text>
          <TouchableOpacity onPress={newChat} style={{ backgroundColor: T.accentDim, paddingHorizontal: 14, paddingVertical: 7, borderRadius: 10 }}>
            <Text style={{ color: T.accent, fontWeight: '600', fontSize: 13 }}>＋ New</Text>
          </TouchableOpacity>
        </View>

        <View style={{ paddingHorizontal: 16, marginBottom: 8 }}>
          <TextInput
            style={{ backgroundColor: T.card, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, fontSize: 14, color: T.t1, borderWidth: 1, borderColor: T.border }}
            value={searchQ} onChangeText={setSearchQ}
            placeholder="Search..." placeholderTextColor={T.t4}
          />
        </View>

        <ScrollView showsVerticalScrollIndicator={false} style={{ flex: 1 }}>
          {filteredConvos.map(c => (
            <Pressable key={c.id}
              style={[{ paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: 1, borderColor: T.border }, activeConvo === c.id && { backgroundColor: T.accentDim }]}
              onPress={() => switchConvo(c)}
              onLongPress={() => Alert.alert(c.title, '', [
                { text: c.pinned ? 'Unpin' : '📌 Pin', onPress: () => pinConvo(c.id) },
                { text: '🗑️ Delete', style: 'destructive', onPress: () => deleteConvo(c.id) },
                { text: 'Cancel', style: 'cancel' },
              ])}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                {c.pinned && <Text style={{ marginRight: 6 }}>📌</Text>}
                <Text style={{ fontSize: 14, color: T.t1, fontWeight: '500', flex: 1 }} numberOfLines={1}>{c.title}</Text>
              </View>
              <Text style={{ fontSize: 11, color: T.t3, marginTop: 2 }}>{c.messages?.length || 0} msgs</Text>
            </Pressable>
          ))}
        </ScrollView>

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14, borderTopWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.t3, fontSize: 12 }}>{userName}</Text>
          <TouchableOpacity onPress={() => { toggleDrawer(false); setSettingsOpen(true); }}>
            <Text style={{ color: T.accent, fontSize: 13 }}>⚙️ Settings</Text>
          </TouchableOpacity>
        </View>
      </Animated.View>

      {/* ══ Header ══ */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <TouchableOpacity onPress={() => toggleDrawer(!drawerOpen)} style={{ marginRight: 14 }}>
            <Text style={{ color: T.t2, fontSize: 22 }}>☰</Text>
          </TouchableOpacity>
          {co?.logo ? (
            <Image source={{ uri: co.logo }} style={{ width: 30, height: 30, borderRadius: 8, marginRight: 10 }} resizeMode="contain" />
          ) : (
            <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: T.accentDim, justifyContent: 'center', alignItems: 'center', marginRight: 10 }}>
              <Text style={{ fontSize: 15, fontWeight: '800', color: T.accent }}>N</Text>
            </View>
          )}
          <View>
            <Text style={{ fontSize: 16, fontWeight: '700', color: T.t1 }}>{co?.company_name || 'Niv AI'}</Text>
            <Text style={{ fontSize: 11, color: streaming ? T.orange : T.green }}>
              {streaming ? (toolInfo ? '⚡ ' + toolInfo : '● Thinking...') : '● Online'}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={() => setQuickActionsOpen(true)} style={{ padding: 6 }}>
            <Text style={{ fontSize: 20 }}>⚡</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={newChat} style={{ padding: 6 }}>
            <Text style={{ color: T.accent, fontSize: 20 }}>✎</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* ══ Messages ══ */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={i => String(i.id)}
        renderItem={renderMsg}
        contentContainerStyle={{ padding: 14, paddingBottom: 8, flexGrow: 1 }}
        onContentSizeChange={() => { if (!showScroll) listRef.current?.scrollToEnd({ animated: true }); }}
        onScroll={(e) => {
          const { contentOffset, layoutMeasurement, contentSize } = e.nativeEvent;
          setShowScroll(contentOffset.y + layoutMeasurement.height < contentSize.height - 100);
        }}
        scrollEventThrottle={100}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={{ alignItems: 'center', paddingTop: 80 }}>
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: T.accentDim, justifyContent: 'center', alignItems: 'center', marginBottom: 14, borderWidth: 2, borderColor: T.accentMid }}>
              <Text style={{ fontSize: 30, fontWeight: '800', color: T.accent }}>N</Text>
            </View>
            <Text style={{ fontSize: 24, fontWeight: '700', color: T.t1 }}>Niv AI</Text>
            <Text style={{ fontSize: 13, color: T.t3, marginTop: 4, marginBottom: 32 }}>{co?.company_name || 'Your AI Assistant'}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 10, paddingHorizontal: 10 }}>
              {suggestions.map((sg, i) => (
                <TouchableOpacity key={i}
                  style={{ width: (SW - 54) / 2, backgroundColor: T.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: T.border }}
                  onPress={() => setInput(sg.text)} activeOpacity={0.7}>
                  <Text style={{ fontSize: 22, marginBottom: 6 }}>{sg.icon}</Text>
                  <Text style={{ fontSize: 13, color: T.t2, lineHeight: 18 }}>{sg.text}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        }
      />

      {/* Scroll button */}
      {showScroll && (
        <TouchableOpacity onPress={() => { listRef.current?.scrollToEnd({ animated: true }); setShowScroll(false); }}
          style={{ position: 'absolute', right: 16, bottom: 80, width: 36, height: 36, borderRadius: 18, backgroundColor: T.elevated, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: T.t4 }} activeOpacity={0.8}>
          <Text style={{ color: T.t1, fontSize: 16 }}>↓</Text>
        </TouchableOpacity>
      )}

      {/* ══ Input ══ */}
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={{ paddingHorizontal: 10, paddingTop: 6, paddingBottom: Platform.OS === 'ios' ? 28 : 8, backgroundColor: T.bg }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', backgroundColor: T.surface, borderRadius: 26, borderWidth: 1, borderColor: T.t4, paddingLeft: 6, paddingRight: 6, paddingVertical: 4 }}>
            {/* Attachment menu */}
            <TouchableOpacity onPress={() => {
              Alert.alert('Attach', '', [
                { text: '📷 Camera', onPress: takePhoto },
                { text: '🖼️ Gallery', onPress: pickImage },
                { text: 'Cancel', style: 'cancel' },
              ]);
            }} style={{ padding: 6, marginRight: 2 }}>
              <Text style={{ fontSize: 20 }}>📎</Text>
            </TouchableOpacity>

            <TextInput
              style={{ flex: 1, fontSize: 16, color: T.t1, maxHeight: 120, paddingVertical: 8, lineHeight: 22 }}
              value={input} onChangeText={setInput}
              placeholder="Message..." placeholderTextColor={T.t4}
              multiline maxLength={2000} blurOnSubmit returnKeyType="send" onSubmitEditing={send}
            />

            {streaming ? (
              <TouchableOpacity onPress={stopStreaming}
                style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: T.red, justifyContent: 'center', alignItems: 'center', marginBottom: 2, marginLeft: 6 }}>
                <Text style={{ color: '#fff', fontSize: 14, fontWeight: '700' }}>■</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: (!input.trim() || loading) ? T.t4 : T.accent, justifyContent: 'center', alignItems: 'center', marginBottom: 2, marginLeft: 6 }}
                onPress={send} disabled={!input.trim() || loading} activeOpacity={0.7}>
                {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={{ color: '#fff', fontSize: 17, fontWeight: '700' }}>↑</Text>}
              </TouchableOpacity>
            )}
          </View>
        </View>
      </KeyboardAvoidingView>

      {/* Modals */}
      <SettingsModal visible={settingsOpen} onClose={() => setSettingsOpen(false)}
        session={session} theme={theme} toggleTheme={toggleTheme}
        biometricEnabled={biometricEnabled} toggleBiometric={toggleBiometric} onLogout={onLogout} />
      <QuickActionsModal visible={quickActionsOpen} onClose={() => setQuickActionsOpen(false)} session={session} />
    </SafeAreaView>
  );
}

// ════════════════════════════════════════════════
// TYPING INDICATOR
// ════════════════════════════════════════════════
function TypingIndicator({ T }) {
  const d1 = useRef(new Animated.Value(0.3)).current;
  const d2 = useRef(new Animated.Value(0.3)).current;
  const d3 = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const a = (v, del) => Animated.loop(Animated.sequence([
      Animated.delay(del),
      Animated.timing(v, { toValue: 1, duration: 300, useNativeDriver: true }),
      Animated.timing(v, { toValue: 0.3, duration: 300, useNativeDriver: true }),
    ]));
    Animated.parallel([a(d1, 0), a(d2, 150), a(d3, 300)]).start();
  }, []);

  return (
    <View style={{ flexDirection: 'row', backgroundColor: T?.card || '#141414', borderRadius: 20, borderTopLeftRadius: 6, paddingVertical: 14, paddingHorizontal: 20, borderWidth: 1, borderColor: T?.border || '#1a1a1a' }}>
      {[d1, d2, d3].map((d, i) => (
        <Animated.View key={i} style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T?.t3 || '#666', marginHorizontal: 3, opacity: d }} />
      ))}
    </View>
  );
}

// ════════════════════════════════════════════════
// BASE STYLES
// ════════════════════════════════════════════════
const st = StyleSheet.create({
  fill: { flex: 1 },
  center: { justifyContent: 'center', alignItems: 'center' },
  nCircle: { width: 88, height: 88, borderRadius: 44, justifyContent: 'center', alignItems: 'center', borderWidth: 2 },
  nLogo: { fontSize: 44, fontWeight: '800' },
  wCircle: { width: 76, height: 76, borderRadius: 38, justifyContent: 'center', alignItems: 'center', borderWidth: 2 },
  fieldLabel: { fontSize: 12, fontWeight: '700', marginBottom: 10, letterSpacing: 2 },
  fieldInput: { borderRadius: 16, paddingHorizontal: 20, paddingVertical: 16, fontSize: 17, borderWidth: 1 },
  mainBtn: { borderRadius: 16, paddingVertical: 17, alignItems: 'center', marginTop: 28, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.3, shadowRadius: 14, elevation: 8 },
  mainBtnT: { color: '#fff', fontSize: 17, fontWeight: '700' },
});
