import React, { useState, useEffect } from 'react'
import axios from 'axios'
import './LoginModal.css'

const TRANSLATIONS = {
  en_GB: {
    name: 'English (UK)',
    tagline: 'HLA Studio helps you govern data architecture, reconcile ETL pipelines, and automate control schedules across your enterprise.',
    feat1: 'Automated enterprise ETL reconciliation pipelines',
    feat2: 'Multi-database RBAC & zero-trust audit governance',
    feat3: 'Zero-config direct failure alerts to external inboxes',
    usernamePlaceholder: 'Username or enterprise email',
    passwordPlaceholder: 'Password',
    show: 'Show',
    hide: 'Hide',
    loginBtn: 'Log In',
    loggingIn: 'Logging in…',
    forgotPassword: 'Forgotten password?',
    enterDirectly: '⚡ Enter HLA Studio Directly',
    portalNotice: 'Enterprise Portal:',
    portalNoticeText: 'Click banner or green button above to bypass login.',
    workspaces: 'Workspaces',
    scheduler: 'Control Scheduler',
    targetDb: 'Target DB Studio',
    rulesCatalog: 'Rules Catalog (R1–R15)',
    workbench: 'Architecture Workbench',
    connectors: 'Universal DB Connectors',
    security: 'Security & RBAC',
    settings: 'System Settings',
    privacy: 'Privacy',
    terms: 'Terms',
    help: 'Help Center',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Meta Architecture Design',
    adminResetAlert: 'To reset admin password, run `python reset_admin.py` on your server.'
  },
  es: {
    name: 'Español',
    tagline: 'HLA Studio te ayuda a gobernar la arquitectura de datos, conciliar pipelines ETL y automatizar cronogramas de control en tu empresa.',
    feat1: 'Pipelines automatizados de conciliación ETL empresarial',
    feat2: 'RBAC multi-base de datos y gobernanza de auditoría zero-trust',
    feat3: 'Alertas directas de fallos sin configuración a bandejas externas',
    usernamePlaceholder: 'Usuario o correo corporativo',
    passwordPlaceholder: 'Contraseña',
    show: 'Mostrar',
    hide: 'Ocultar',
    loginBtn: 'Iniciar sesión',
    loggingIn: 'Iniciando sesión…',
    forgotPassword: '¿Olvidaste tu contraseña?',
    enterDirectly: '⚡ Entrar a HLA Studio Directamente',
    portalNotice: 'Portal Corporativo:',
    portalNoticeText: 'Haz clic en el banner o en el botón verde para omitir el inicio de sesión.',
    workspaces: 'Espacios de trabajo',
    scheduler: 'Programador de Control',
    targetDb: 'Target DB Studio',
    rulesCatalog: 'Catálogo de Reglas (R1–R15)',
    workbench: 'Banco de Arquitectura',
    connectors: 'Conectores Universales DB',
    security: 'Seguridad y RBAC',
    settings: 'Configuración del Sistema',
    privacy: 'Privacidad',
    terms: 'Condiciones',
    help: 'Centro de ayuda',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Diseño de Arquitectura Meta',
    adminResetAlert: 'Para restablecer la contraseña de administrador, ejecuta `python reset_admin.py` en tu servidor.'
  },
  fr: {
    name: 'Français (France)',
    tagline: 'HLA Studio vous aide à gouverner l’architecture des données, réconcilier les flux ETL et automatiser les plannings de contrôle dans votre entreprise.',
    feat1: 'Pipelines automatisés de réconciliation ETL d’entreprise',
    feat2: 'RBAC multi-bases de données et gouvernance d’audit zero-trust',
    feat3: 'Alertes directes d’échec sans configuration vers les boîtes externes',
    usernamePlaceholder: 'Nom d’utilisateur ou e-mail d’entreprise',
    passwordPlaceholder: 'Mot de passe',
    show: 'Afficher',
    hide: 'Masquer',
    loginBtn: 'Se connecter',
    loggingIn: 'Connexion en cours…',
    forgotPassword: 'Mot de passe oublié ?',
    enterDirectly: '⚡ Entrer dans HLA Studio Directement',
    portalNotice: 'Portail d’Entreprise :',
    portalNoticeText: 'Cliquez sur la bannière ou le bouton vert ci-dessus pour ignorer la connexion.',
    workspaces: 'Espaces de travail',
    scheduler: 'Planificateur de Contrôle',
    targetDb: 'Studio Target DB',
    rulesCatalog: 'Catalogue de Règles (R1–R15)',
    workbench: 'Établi d’Architecture',
    connectors: 'Connecteurs Universels DB',
    security: 'Sécurité & RBAC',
    settings: 'Paramètres Système',
    privacy: 'Confidentialité',
    terms: 'Conditions',
    help: 'Centre d’aide',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Conception d’Architecture Meta',
    adminResetAlert: 'Pour réinitialiser le mot de passe administrateur, exécutez `python reset_admin.py` sur votre serveur.'
  },
  de: {
    name: 'Deutsch',
    tagline: 'HLA Studio unterstützt Sie bei der Verwaltung von Datenarchitekturen, dem Abgleich von ETL-Pipelines und der Automatisierung von Kontrollzeitplänen im gesamten Unternehmen.',
    feat1: 'Automatisierte ETL-Abgleich-Pipelines für Unternehmen',
    feat2: 'Multi-Datenbank-RBAC & Zero-Trust-Audit-Governance',
    feat3: 'Konfigurationsfreie Ausfallwarnungen direkt an externe Postfächer',
    usernamePlaceholder: 'Benutzername oder Unternehmens-E-Mail',
    passwordPlaceholder: 'Passwort',
    show: 'Anzeigen',
    hide: 'Verbergen',
    loginBtn: 'Anmelden',
    loggingIn: 'Anmeldung läuft…',
    forgotPassword: 'Passwort vergessen?',
    enterDirectly: '⚡ Direkt zu HLA Studio wechseln',
    portalNotice: 'Unternehmensportal:',
    portalNoticeText: 'Klicken Sie auf das Banner oder den grünen Button, um die Anmeldung zu überspringen.',
    workspaces: 'Arbeitsbereiche',
    scheduler: 'Steuerungszeitplan',
    targetDb: 'Target DB Studio',
    rulesCatalog: 'Regelkatalog (R1–R15)',
    workbench: 'Architektur-Workbench',
    connectors: 'Universelle DB-Connectors',
    security: 'Sicherheit & RBAC',
    settings: 'Systemeinstellungen',
    privacy: 'Datenschutz',
    terms: 'Nutzungsbedingungen',
    help: 'Hilfebereich',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Meta-Architekturdesign',
    adminResetAlert: 'Um das Administrator-Passwort zurückzusetzen, führen Sie `python reset_admin.py` auf Ihrem Server aus.'
  },
  it: {
    name: 'Italiano',
    tagline: 'HLA Studio ti aiuta a governare l’architettura dei dati, riconciliare le pipeline ETL e automatizzare le pianificazioni di controllo in tutta l’azienda.',
    feat1: 'Pipeline automatizzate di riconciliazione ETL aziendale',
    feat2: 'RBAC multi-database e governance di audit zero-trust',
    feat3: 'Avvisi diretti di errore senza configurazione alle caselle esterne',
    usernamePlaceholder: 'Nome utente o email aziendale',
    passwordPlaceholder: 'Password',
    show: 'Mostra',
    hide: 'Nascondi',
    loginBtn: 'Accedi',
    loggingIn: 'Accesso in corso…',
    forgotPassword: 'Password dimenticata?',
    enterDirectly: '⚡ Entra direttamente in HLA Studio',
    portalNotice: 'Portale Aziendale:',
    portalNoticeText: 'Fai clic sul banner o sul pulsante verde per saltare l’accesso.',
    workspaces: 'Aree di lavoro',
    scheduler: 'Pianificatore di Controllo',
    targetDb: 'Target DB Studio',
    rulesCatalog: 'Catalogo Regole (R1–R15)',
    workbench: 'Banco di Architettura',
    connectors: 'Connettori Universali DB',
    security: 'Sicurezza e RBAC',
    settings: 'Impostazioni di Sistema',
    privacy: 'Privacy',
    terms: 'Termini',
    help: 'Centro assistenza',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Progettazione Architettura Meta',
    adminResetAlert: 'Per reimpostare la password amministratore, esegui `python reset_admin.py` sul server.'
  },
  pt_BR: {
    name: 'Português (Brasil)',
    tagline: 'O HLA Studio ajuda você a governar a arquitetura de dados, reconciliar pipelines ETL e automatizar agendamentos de controle em toda a empresa.',
    feat1: 'Pipelines automatizados de reconciliação ETL empresarial',
    feat2: 'RBAC multi-banco de dados e governança de auditoria zero-trust',
    feat3: 'Alertas diretos de falha sem configuração para caixas de entrada externas',
    usernamePlaceholder: 'Nome de usuário ou e-mail corporativo',
    passwordPlaceholder: 'Senha',
    show: 'Mostrar',
    hide: 'Ocultar',
    loginBtn: 'Entrar',
    loggingIn: 'Entrando…',
    forgotPassword: 'Esqueceu a senha?',
    enterDirectly: '⚡ Entrar no HLA Studio Diretamente',
    portalNotice: 'Portal Corporativo:',
    portalNoticeText: 'Clique no banner ou no botão verde acima para pular o login.',
    workspaces: 'Espaços de Trabalho',
    scheduler: 'Agendador de Controle',
    targetDb: 'Target DB Studio',
    rulesCatalog: 'Catálogo de Regras (R1–R15)',
    workbench: 'Bancada de Arquitetura',
    connectors: 'Conectores Universais DB',
    security: 'Segurança e RBAC',
    settings: 'Configurações do Sistema',
    privacy: 'Privacidade',
    terms: 'Termos',
    help: 'Central de Ajuda',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Design de Arquitetura Meta',
    adminResetAlert: 'Para redefinir a senha do administrador, execute `python reset_admin.py` em seu servidor.'
  },
  hi: {
    name: 'हिन्दी',
    tagline: 'HLA Studio आपके डेटा आर्किटेक्चर को नियंत्रित करने, ETL पाइपलाइन का मिलान करने और आपके उद्यम में नियंत्रण शेड्यूलिंग को स्वचालित करने में मदद करता है।',
    feat1: 'स्वचालित उद्यम ETL समाधान एवं सामंजस्य पाइपलाइन',
    feat2: 'मल्टी-डेटाबेस RBAC और ज़ीरो-ट्रस्ट ऑडिट प्रशासन',
    feat3: 'बाहरी इनबॉक्स में बिना कॉन्फ़िगरेशन सीधे विफलता अलर्ट',
    usernamePlaceholder: 'उपयोगकर्ता नाम या उद्यम ईमेल',
    passwordPlaceholder: 'पासवर्ड',
    show: 'दिखाएँ',
    hide: 'छिपाएँ',
    loginBtn: 'लॉग इन करें',
    loggingIn: 'लॉग इन हो रहा है…',
    forgotPassword: 'पासवर्ड भूल गए?',
    enterDirectly: '⚡ सीधे HLA Studio में प्रवेश करें',
    portalNotice: 'उद्यम पोर्टल:',
    portalNoticeText: 'लॉगिन को बायपास करने के लिए ऊपर बैनर या हरे बटन पर क्लिक करें।',
    workspaces: 'कार्यस्थान (Workspaces)',
    scheduler: 'कंट्रोल शेड्यूलर',
    targetDb: 'टारगेट डीबी स्टूडियो',
    rulesCatalog: 'नियम सूची (R1–R15)',
    workbench: 'आर्किटेक्चर वर्कबेंच',
    connectors: 'यूनिवर्सल डेटाबेस कनेक्टर्स',
    security: 'सुरक्षा और RBAC',
    settings: 'सिस्टम सेटिंग्स',
    privacy: 'गोपनीयता',
    terms: 'शर्तें',
    help: 'सहायता केंद्र',
    copyright: 'HLA Studio © 2026 Enterprise Edition • मेटा आर्किटेक्चर डिज़ाइन',
    adminResetAlert: 'व्यवस्थापक पासवर्ड रीसेट करने के लिए, सर्वर पर `python reset_admin.py` चलाएँ।'
  },
  ar: {
    name: 'العربية',
    tagline: 'يساعدك HLA Studio على حوكمة هندسة البيانات، وتسوية خطوط أنابيب ETL، وأتمتة جداول التحكم عبر مؤسستك بأكملها.',
    feat1: 'خطوط أنابيب تسوية ETL مؤتمتة للمؤسسات',
    feat2: 'حوكمة تدقيق RBAC متعدد قواعد البيانات مع انعدام الثقة (Zero-Trust)',
    feat3: 'تنبيهات فورية ومباشرة عند الفشل إلى البريد الخارجي دون إعدادات معقدة',
    usernamePlaceholder: 'اسم المستخدم أو البريد الإلكتروني للعمل',
    passwordPlaceholder: 'كلمة المرور',
    show: 'إظهار',
    hide: 'إخفاء',
    loginBtn: 'تسجيل الدخول',
    loggingIn: 'جارٍ تسجيل الدخول…',
    forgotPassword: 'هل نسيت كلمة المرور؟',
    enterDirectly: '⚡ الدخول مباشرة إلى HLA Studio',
    portalNotice: 'بوابة المؤسسة:',
    portalNoticeText: 'انقر على الشعار أو الزر الأخضر أعلاه لتجاوز تسجيل الدخول.',
    workspaces: 'مساحات العمل',
    scheduler: 'جدولة التحكم',
    targetDb: 'استوديو قاعدة البيانات الهدف',
    rulesCatalog: 'كتالوج القواعد (R1–R15)',
    workbench: 'منصة الهندسة المعمارية',
    connectors: 'موصلات قواعد البيانات الشاملة',
    security: 'الأمان وإدارة الأدوار',
    settings: 'إعدادات النظام',
    privacy: 'الخصوصية',
    terms: 'الشروط',
    help: 'مركز المساعدة',
    copyright: 'HLA Studio © 2026 Enterprise Edition • تصميم الهندسة المتقدمة',
    adminResetAlert: 'لإعادة تعيين كلمة مرور المسؤول، شغّل `python reset_admin.py` على الخادم.'
  },
  ja: {
    name: '日本語',
    tagline: 'HLA Studio は、企業全体でのデータアーキテクチャのガバナンス、ETLパイプラインの照合、および制御スケジュールの自動化を支援します。',
    feat1: '自動化されたエンタープライズETL照合パイプライン',
    feat2: 'マルチデータベース RBAC およびゼロトラスト監査ガバナンス',
    feat3: '設定不要の外部メールへのダイレクト障害通知',
    usernamePlaceholder: 'ユーザー名または企業メールアドレス',
    passwordPlaceholder: 'パスワード',
    show: '表示',
    hide: '非表示',
    loginBtn: 'ログイン',
    loggingIn: 'ログイン中…',
    forgotPassword: 'パスワードをお忘れですか？',
    enterDirectly: '⚡ HLA Studio に直接入る',
    portalNotice: 'エンタープライズポータル:',
    portalNoticeText: '上のバナーまたは緑のボタンをクリックするとログインをスキップできます。',
    workspaces: 'ワークスペース',
    scheduler: 'コントロールスケジューラー',
    targetDb: 'ターゲットDBスタジオ',
    rulesCatalog: 'ルールカタログ (R1–R15)',
    workbench: 'アーキテクチャワークベンチ',
    connectors: 'ユニバーサルDBコネクタ',
    security: 'セキュリティ & RBAC',
    settings: 'システム設定',
    privacy: 'プライバシー',
    terms: '利用規約',
    help: 'ヘルプセンター',
    copyright: 'HLA Studio © 2026 Enterprise Edition • メタアーキテクチャ設計',
    adminResetAlert: '管理者パスワードを再設定するには、サーバーで `python reset_admin.py` を実行してください。'
  },
  zh: {
    name: '中文 (简体)',
    tagline: 'HLA Studio 帮助您管控数据架构、对账 ETL 数据管道，并自动化全企业的合规控制排程。',
    feat1: '企业级自动化 ETL 对账与核算管道',
    feat2: '通用多数据库 RBAC 与零信任审计治理',
    feat3: '零配置直接向外部邮箱发送故障告警',
    usernamePlaceholder: '用户名或企业邮箱',
    passwordPlaceholder: '密码',
    show: '显示',
    hide: '隐藏',
    loginBtn: '登录',
    loggingIn: '正在登录…',
    forgotPassword: '忘记密码？',
    enterDirectly: '⚡ 直接进入 HLA Studio',
    portalNotice: '企业级门户：',
    portalNoticeText: '点击上方横幅或绿色按钮可直接跳过登录。',
    workspaces: '工作区 (Workspaces)',
    scheduler: '控制调度器',
    targetDb: '目标数据库工作台',
    rulesCatalog: '规则目录 (R1–R15)',
    workbench: '架构工作台',
    connectors: '通用多数据库连接器',
    security: '安全与 RBAC',
    settings: '系统设置',
    privacy: '隐私政策',
    terms: '服务条款',
    help: '帮助中心',
    copyright: 'HLA Studio © 2026 企业版 • 元架构设计',
    adminResetAlert: '如需重置管理员密码，请在服务器上运行 `python reset_admin.py`。'
  },
  ru: {
    name: 'Русский',
    tagline: 'HLA Studio помогает управлять архитектурой данных, сверять ETL-конвейеры и автоматизировать расписания контроля на вашем предприятии.',
    feat1: 'Автоматизированные конвейеры сверки корпоративных ETL',
    feat2: 'Многобазовый RBAC и аудит-контроль zero-trust',
    feat3: 'Прямые оповещения о сбоях на внешние почтовые ящики без настройки',
    usernamePlaceholder: 'Имя пользователя или корпоративная почта',
    passwordPlaceholder: 'Пароль',
    show: 'Показать',
    hide: 'Скрыть',
    loginBtn: 'Войти',
    loggingIn: 'Вход в систему…',
    forgotPassword: 'Забыли пароль?',
    enterDirectly: '⚡ Войти в HLA Studio напрямую',
    portalNotice: 'Корпоративный портал:',
    portalNoticeText: 'Нажмите на баннер или зеленую кнопку выше, чтобы пропустить вход.',
    workspaces: 'Рабочие пространства',
    scheduler: 'Планировщик контроля',
    targetDb: 'Target DB Studio',
    rulesCatalog: 'Каталог правил (R1–R15)',
    workbench: 'Архитектурный верстак',
    connectors: 'Универсальные коннекторы DB',
    security: 'Безопасность и RBAC',
    settings: 'Системные настройки',
    privacy: 'Конфиденциальность',
    terms: 'Условия',
    help: 'Справочный центр',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Дизайн Meta Architecture',
    adminResetAlert: 'Чтобы сбросить пароль администратора, выполните `python reset_admin.py` на сервере.'
  },
  ko: {
    name: '한국어',
    tagline: 'HLA Studio는 엔터프라이즈 전반에서 데이터 아키텍처를 관리하고, ETL 파이프라인을 조정하며, 제어 일정을 자동화하도록 지원합니다.',
    feat1: '자동화된 엔터프라이즈 ETL 대사 파이프라인',
    feat2: '멀티 데이터베이스 RBAC 및 제로 트러스트 감사 거버넌스',
    feat3: '외부 수신함으로 설정 없이 즉시 전달되는 장애 알림',
    usernamePlaceholder: '사용자 이름 또는 회사 이메일',
    passwordPlaceholder: '비밀번호',
    show: '표시',
    hide: '숨기기',
    loginBtn: '로그인',
    loggingIn: '로그인 중…',
    forgotPassword: '비밀번호를 잊으셨나요?',
    enterDirectly: '⚡ HLA Studio 바로 입장',
    portalNotice: '엔터프라이즈 포털:',
    portalNoticeText: '로그인을 건너뛰려면 상단 배너나 녹색 버튼을 클릭하세요.',
    workspaces: '워크스페이스',
    scheduler: '제어 스케줄러',
    targetDb: '타깃 DB 스튜디오',
    rulesCatalog: '규칙 카탈로그 (R1–R15)',
    workbench: '아키텍처 워크벤치',
    connectors: '범용 DB 커넥터',
    security: '보안 및 RBAC',
    settings: '시스템 설정',
    privacy: '개인정보 보호',
    terms: '이용 약관',
    help: '고객 센터',
    copyright: 'HLA Studio © 2026 Enterprise Edition • Meta 아키텍처 디자인',
    adminResetAlert: '관리자 비밀번호를 재설정하려면 서버에서 `python reset_admin.py`를 실행하세요.'
  }
}

const FOOTER_LANGUAGES = [
  { key: 'en_GB', label: 'English (UK)' },
  { key: 'es', label: 'Español' },
  { key: 'fr', label: 'Français (France)' },
  { key: 'de', label: 'Deutsch' },
  { key: 'it', label: 'Italiano' },
  { key: 'pt_BR', label: 'Português (Brasil)' },
  { key: 'hi', label: 'हिन्दी' },
  { key: 'ar', label: 'العربية' },
  { key: 'ja', label: '日本語' },
]

export default function LoginModal({ isOpen, onLoginSuccess, onClose, currentRole }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  
  // Interactive Language State
  const [currentLang, setCurrentLang] = useState(() => {
    return localStorage.getItem('hla_lang') || 'en_GB'
  })
  const [showLangModal, setShowLangModal] = useState(false)

  // Forgot Password Enterprise Workflow State (Email OTP Flow)
  const [showForgotWizard, setShowForgotWizard] = useState(false)
  const [wizardStep, setWizardStep] = useState('request') // 'request' | 'otp' | 'reset' | 'success'
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotError, setForgotError] = useState('')
  const [serverNotice, setServerNotice] = useState('')

  // OTP Verification Step States
  const [enteredOtp, setEnteredOtp] = useState('')
  const [otpVerifying, setOtpVerifying] = useState(false)
  const [otpError, setOtpError] = useState('')
  const [resendCooldown, setResendCooldown] = useState(0)
  const [expirySeconds, setExpirySeconds] = useState(600)

  // Reset Password Step States
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [tokenResetLoading, setTokenResetLoading] = useState(false)
  const [tokenResetError, setTokenResetError] = useState('')
  const [successNotice, setSuccessNotice] = useState('')

  // Live countdown timers for OTP expiry and Resend cooldown
  useEffect(() => {
    let interval = null
    if (showForgotWizard && wizardStep === 'otp') {
      interval = setInterval(() => {
        setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0))
        setExpirySeconds((prev) => (prev > 0 ? prev - 1 : 0))
      }, 1000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [showForgotWizard, wizardStep])

  const formatExpiry = (sec) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`
  }

  if (!isOpen) return null

  const t = TRANSLATIONS[currentLang] || TRANSLATIONS.en_GB
  const isRTL = currentLang === 'ar'

  const handleSelectLang = (langKey) => {
    setCurrentLang(langKey)
    localStorage.setItem('hla_lang', langKey)
    setShowLangModal(false)
  }

  const handleOpenForgotWizard = () => {
    setWizardStep('request')
    setForgotEmail(username && username.includes('@') ? username : '')
    setForgotError('')
    setServerNotice('')
    setEnteredOtp('')
    setOtpError('')
    setResetToken('')
    setNewPassword('')
    setConfirmPassword('')
    setTokenResetError('')
    setSuccessNotice('')
    setShowForgotWizard(true)
  }

  const handleSendOtp = async (e) => {
    if (e) e.preventDefault()
    const emailToSubmit = forgotEmail.trim().toLowerCase()
    if (!emailToSubmit) {
      setForgotError('Please enter your registered email address.')
      return
    }
    setForgotLoading(true)
    setForgotError('')
    setOtpError('')

    try {
      const res = await axios.post('/api/auth/forgot-password', {
        email: emailToSubmit
      })
      setServerNotice(res.data?.message || 'A 6-digit verification code has been sent to your registered email.')
      setWizardStep('otp')
      setEnteredOtp('')
      setResendCooldown(60)
      setExpirySeconds(600)
    } catch (err) {
      const errMsg = err.response?.data?.error || 'Unable to send the verification email. Please try again later.'
      setForgotError(errMsg)
      if (wizardStep === 'otp') {
        setOtpError(errMsg)
      }
    } finally {
      setForgotLoading(false)
    }
  }

  const handleVerifyOtp = async (e) => {
    if (e) e.preventDefault()
    const cleanOtp = enteredOtp.trim()
    if (!cleanOtp) {
      setOtpError('Invalid verification code. Please try again.')
      return
    }
    setOtpVerifying(true)
    setOtpError('')

    try {
      const res = await axios.post('/api/auth/verify-otp', {
        email: forgotEmail.trim().toLowerCase(),
        otp: cleanOtp
      })
      if (res.data.success && res.data.reset_token) {
        setResetToken(res.data.reset_token)
        setWizardStep('reset')
      } else {
        setOtpError(res.data.error || 'Invalid verification code. Please try again.')
      }
    } catch (err) {
      setOtpError(err.response?.data?.error || 'Invalid verification code. Please try again.')
    } finally {
      setOtpVerifying(false)
    }
  }

  const handlePerformResetPassword = async (e) => {
    e.preventDefault()
    if (newPassword !== confirmPassword) {
      setTokenResetError('Passwords do not match.')
      return
    }
    setTokenResetLoading(true)
    setTokenResetError('')

    try {
      const res = await axios.post('/api/auth/reset-password', {
        reset_token: resetToken,
        new_password: newPassword,
        confirm_password: confirmPassword
      })

      // Clean address bar query string if present
      const cleanUrl = window.location.origin + window.location.pathname
      window.history.replaceState({}, document.title, cleanUrl)

      setWizardStep('success')
      setSuccessNotice(res.data?.message || 'Password reset successful. Please log in with your new password.')
      setUsername(forgotEmail)
      setPassword('')
    } catch (err) {
      setTokenResetError(err.response?.data?.error || 'Failed to update password. Ensure it satisfies all policy requirements.')
    } finally {
      setTokenResetLoading(false)
    }
  }

  const policyChecks = {
    length: newPassword.length >= 8,
    upper: /[A-Z]/.test(newPassword),
    lower: /[a-z]/.test(newPassword),
    number: /[0-9]/.test(newPassword),
    special: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?~`]/.test(newPassword),
    match: newPassword.length > 0 && confirmPassword.length > 0 && newPassword === confirmPassword
  }
  const isPolicyValid = policyChecks.length && policyChecks.upper && policyChecks.lower && policyChecks.number && policyChecks.special && policyChecks.match

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMsg('')
    setLoading(true)

    try {
      const res = await axios.post('/api/auth/login', {
        username: username.trim(),
        password: password.trim(),
      })
      const { token, access_token, refresh_token, user } = res.data
      const activeToken = access_token || token
      if (refresh_token) localStorage.setItem('refresh_token', refresh_token)
      if (activeToken) {
        localStorage.setItem('access_token', activeToken)
        localStorage.setItem('hla_token', activeToken)
      }
      onLoginSuccess(user, activeToken)
    } catch (err) {
      if (!err.response) {
        setErrorMsg('Cannot connect to backend server. Ensure Flask backend is running on port 5000.')
      } else if (err.response.status === 500) {
        setErrorMsg('Database connection error on server. Verify PostgreSQL credentials in .env.')
      } else {
        setErrorMsg(err.response.data?.error || 'The username or password you entered is incorrect.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fb-login-viewport" dir={isRTL ? 'rtl' : 'ltr'}>
      <div className="fb-content-wrapper">
        <div className="fb-login-container">
          
          {/* ── Left Side: Facebook-Style Brand Hero ── */}
          <div className="fb-hero-section">
            <div className="fb-brand-title">
              HLA Studio
            </div>
            <h2 className="fb-hero-tagline">
              {t.tagline}
            </h2>
            <div className="fb-hero-features">
              <div className="fb-feat-item">
                <span className="fb-feat-bullet">✓</span>
                <span>{t.feat1}</span>
              </div>
              <div className="fb-feat-item">
                <span className="fb-feat-bullet">✓</span>
                <span>{t.feat2}</span>
              </div>
              <div className="fb-feat-item">
                <span className="fb-feat-bullet">✓</span>
                <span>{t.feat3}</span>
              </div>
            </div>
          </div>

          {/* ── Right Side: Facebook-Style Login Card ── */}
          <div className="fb-card-section">
            <div className="fb-login-card" id="login-modal">
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className="fb-close-btn"
                  aria-label="Close"
                  title="Close login"
                >
                  ✕
                </button>
              )}

              {errorMsg && (
                <div className="fb-error-box">
                  <span className="fb-error-icon">⚠️</span>
                  <span>{errorMsg}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="fb-login-form">
                <div className="fb-input-wrapper">
                  <input
                    type="text"
                    className="fb-input-field"
                    placeholder={t.usernamePlaceholder}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    autoFocus
                    id="fb-username-input"
                  />
                </div>

                <div className="fb-input-wrapper fb-pwd-wrapper">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="fb-input-field"
                    placeholder={t.passwordPlaceholder}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    id="fb-password-input"
                  />
                  <button
                    type="button"
                    className="fb-pwd-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    title={showPassword ? t.hide : t.show}
                    aria-label="Toggle password visibility"
                  >
                    {showPassword ? t.hide : t.show}
                  </button>
                </div>

                <button
                  type="submit"
                  className="fb-btn-login"
                  disabled={loading || !username.trim() || !password.trim()}
                  id="fb-btn-submit"
                >
                  {loading ? t.loggingIn : t.loginBtn}
                </button>

                <div className="fb-forgot-link">
                  <button
                    type="button"
                    className="fb-forgot-btn"
                    onClick={handleOpenForgotWizard}
                  >
                    {t.forgotPassword}
                  </button>
                </div>
              </form>
            </div>
          </div>

        </div>
      </div>

      {/* ── Facebook-Style Language & Footer Bar ── */}
      <footer className="fb-portal-footer">
        <div className="fb-footer-inner">
          <div className="fb-footer-langs">
            {FOOTER_LANGUAGES.map((l) => (
              <span
                key={l.key}
                className={currentLang === l.key ? 'fb-active-lang' : ''}
                onClick={() => handleSelectLang(l.key)}
                role="button"
                tabIndex={0}
                title={`Switch language to ${l.label}`}
              >
                {l.label}
              </span>
            ))}
            <button
              className="fb-lang-more"
              type="button"
              onClick={() => setShowLangModal(true)}
              title="More languages"
              aria-label="More languages"
            >
              +
            </button>
          </div>
        </div>
      </footer>

      {/* ── More Languages Popover Modal ── */}
      {showLangModal && (
        <div className="fb-lang-popover-backdrop" onClick={() => setShowLangModal(false)}>
          <div className="fb-lang-popover" onClick={(e) => e.stopPropagation()}>
            <div className="fb-lang-popover-header">
              <h3>Select Language / भाषा चुनें / اختر اللغة</h3>
              <button
                type="button"
                className="fb-lang-popover-close"
                onClick={() => setShowLangModal(false)}
              >
                ✕
              </button>
            </div>
            <div className="fb-lang-grid">
              {Object.entries(TRANSLATIONS).map(([key, item]) => (
                <button
                  key={key}
                  type="button"
                  className={`fb-lang-item ${currentLang === key ? 'active' : ''}`}
                  onClick={() => handleSelectLang(key)}
                >
                  <span>{item.name}</span>
                  {currentLang === key && <span>✓</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Real Email OTP Password Reset Flow ── */}
      {showForgotWizard && (
        <div className="fb-lang-popover-backdrop" onClick={() => setShowForgotWizard(false)}>
          <div className="fb-reset-modal fb-wizard-modal" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="fb-lang-popover-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <span style={{ fontSize: '1.3rem' }}>🔐</span>
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600 }}>
                  {wizardStep === 'request' && 'Reset Password'}
                  {wizardStep === 'otp' && 'Verify Your Email'}
                  {wizardStep === 'reset' && 'Set New Password'}
                  {wizardStep === 'success' && 'Password Reset Successful'}
                </h3>
              </div>
              <button
                type="button"
                className="fb-lang-popover-close"
                onClick={() => setShowForgotWizard(false)}
                title="Close"
              >
                ✕
              </button>
            </div>

            <div className="fb-reset-body">
              {/* Step Tracker Indicator */}
              <div className="fb-wizard-stepper">
                <div className={`fb-step-pill ${wizardStep === 'request' ? 'active' : wizardStep !== 'request' ? 'done' : ''}`}>
                  1. Reset Password
                </div>
                <div className="fb-step-arrow">→</div>
                <div className={`fb-step-pill ${wizardStep === 'otp' ? 'active' : wizardStep === 'reset' || wizardStep === 'success' ? 'done' : ''}`}>
                  2. Verify Email
                </div>
                <div className="fb-step-arrow">→</div>
                <div className={`fb-step-pill ${wizardStep === 'reset' ? 'active' : wizardStep === 'success' ? 'done' : ''}`}>
                  3. Set New Password
                </div>
              </div>

              {/* STEP 1: Enter Email */}
              {wizardStep === 'request' && (
                <div className="fb-wizard-content">
                  <h4 style={{ margin: '0 0 0.5rem 0', color: '#f0f6fc', fontSize: '1.1rem' }}>Reset Password</h4>
                  <p className="fb-reset-desc" style={{ marginBottom: '1rem', color: '#8b949e' }}>
                    Enter your registered email address.
                  </p>

                  {forgotError && (
                    <div className="fb-reset-feedback error">
                      <span>⚠️</span>
                      <span>{forgotError}</span>
                    </div>
                  )}

                  <form onSubmit={handleSendOtp} className="fb-reset-form">
                    <div className="fb-reset-field-col">
                      <label htmlFor="forgot-email-input" style={{ fontWeight: 600, color: '#c9d1d9', marginBottom: '0.35rem' }}>
                        Email Address
                      </label>
                      <input
                        id="forgot-email-input"
                        type="email"
                        className="fb-reset-input"
                        placeholder="user@example.com"
                        value={forgotEmail}
                        onChange={(e) => setForgotEmail(e.target.value)}
                        autoFocus
                        required
                      />
                    </div>

                    <div className="fb-reset-btn-row" style={{ marginTop: '1.25rem', display: 'flex', justifyContent: 'flex-end', gap: '0.6rem' }}>
                      <button
                        type="button"
                        className="fb-btn-close-reset"
                        onClick={() => setShowForgotWizard(false)}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="fb-btn-perform-reset"
                        disabled={forgotLoading || !forgotEmail.trim()}
                        id="send-otp-btn"
                      >
                        {forgotLoading ? 'Sending…' : 'Send OTP'}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* STEP 2: Verify OTP */}
              {wizardStep === 'otp' && (
                <div className="fb-wizard-content fb-sent-content">
                  <h4 style={{ margin: '0 0 0.4rem 0', color: '#f0f6fc', fontSize: '1.15rem' }}>Verify Your Email</h4>
                  <p className="fb-sent-msg" style={{ margin: '0 0 0.8rem 0', color: '#c9d1d9' }}>
                    We've sent a 6-digit verification code to your registered email.
                  </p>

                  <div className="fb-sent-notice-box" style={{
                    background: 'rgba(56, 139, 253, 0.1)',
                    border: '1px solid rgba(56, 139, 253, 0.3)',
                    borderRadius: '8px',
                    padding: '0.6rem 0.9rem',
                    color: '#58a6ff',
                    fontSize: '0.85rem',
                    marginBottom: '1rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    <span>ℹ️</span>
                    <span>{serverNotice || 'A 6-digit verification code has been sent to your registered email.'}</span>
                  </div>

                  <form onSubmit={handleVerifyOtp} className="fb-reset-form" style={{ width: '100%', maxWidth: '420px', margin: '0 auto' }}>
                    {otpError && (
                      <div className="fb-reset-feedback error" style={{ marginBottom: '0.75rem' }}>
                        <span>⚠️</span>
                        <span>{otpError}</span>
                      </div>
                    )}

                    <div className="fb-reset-field-col" style={{ alignItems: 'center' }}>
                      <input
                        id="otp-input"
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={6}
                        className="fb-otp-code-input"
                        placeholder="_ _ _ _ _ _"
                        value={enteredOtp}
                        onChange={(e) => {
                          const val = e.target.value.replace(/\D/g, '').slice(0, 6)
                          setEnteredOtp(val)
                          if (val.length === 6) setOtpError('')
                        }}
                        autoFocus
                        required
                        style={{
                          letterSpacing: '0.4rem',
                          textAlign: 'center',
                          fontSize: '1.5rem',
                          fontWeight: 700,
                          padding: '0.6rem 1rem',
                          width: '220px',
                          background: '#0d1117',
                          border: '1px solid #30363d',
                          borderRadius: '8px',
                          color: '#f0f6fc'
                        }}
                      />
                      <div style={{ marginTop: '0.6rem', fontSize: '0.82rem', color: expirySeconds > 0 ? '#8b949e' : '#f85149' }}>
                        ⏱️ Code expires in <strong>{formatExpiry(expirySeconds)}</strong>
                      </div>
                    </div>

                    <div className="fb-reset-btn-row" style={{ marginTop: '1.25rem', width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <button
                        type="button"
                        className="fb-btn-resend-link"
                        onClick={handleSendOtp}
                        disabled={forgotLoading || resendCooldown > 0}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: resendCooldown > 0 ? '#484f58' : '#58a6ff',
                          cursor: resendCooldown > 0 ? 'not-allowed' : 'pointer',
                          fontSize: '0.86rem',
                          textDecoration: resendCooldown > 0 ? 'none' : 'underline'
                        }}
                      >
                        {forgotLoading ? 'Resending…' : `Resend OTP${resendCooldown > 0 ? ` (${resendCooldown}s)` : ''}`}
                      </button>

                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          type="button"
                          className="fb-btn-close-reset"
                          onClick={() => setShowForgotWizard(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="fb-btn-perform-reset"
                          disabled={otpVerifying || enteredOtp.trim().length !== 6 || expirySeconds <= 0}
                          id="verify-otp-btn"
                        >
                          {otpVerifying ? 'Verifying…' : 'Verify OTP'}
                        </button>
                      </div>
                    </div>
                  </form>
                </div>
              )}

              {/* STEP 3: Set New Password */}
              {wizardStep === 'reset' && (
                <div className="fb-wizard-content">
                  <h4 style={{ margin: '0 0 0.5rem 0', color: '#f0f6fc', fontSize: '1.15rem' }}>Set New Password</h4>
                  <p className="fb-reset-desc" style={{ marginBottom: '1rem', color: '#8b949e' }}>
                    Create a strong, secure password for your HLA Studio account.
                  </p>

                  {tokenResetError && (
                    <div className="fb-reset-feedback error" style={{ marginBottom: '0.75rem' }}>
                      <span>⚠️</span>
                      <span>{tokenResetError}</span>
                    </div>
                  )}

                  <form onSubmit={handlePerformResetPassword} className="fb-reset-form">
                    <div className="fb-reset-inputs-row">
                      <div className="fb-reset-field-col">
                        <label htmlFor="new-pwd-input" style={{ fontWeight: 600, color: '#c9d1d9', marginBottom: '0.35rem' }}>
                          New Password:
                        </label>
                        <input
                          id="new-pwd-input"
                          type={showNewPassword ? 'text' : 'password'}
                          className="fb-reset-input"
                          placeholder="••••••••"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          required
                          autoFocus
                        />
                      </div>
                      <div className="fb-reset-field-col">
                        <label htmlFor="confirm-pwd-input" style={{ fontWeight: 600, color: '#c9d1d9', marginBottom: '0.35rem' }}>
                          Confirm Password:
                        </label>
                        <input
                          id="confirm-pwd-input"
                          type={showNewPassword ? 'text' : 'password'}
                          className="fb-reset-input"
                          placeholder="••••••••"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          required
                        />
                      </div>
                    </div>

                    <div className="fb-show-pwd-toggle" style={{ margin: '0.6rem 0' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.84rem', color: '#8b949e' }}>
                        <input
                          type="checkbox"
                          checked={showNewPassword}
                          onChange={(e) => setShowNewPassword(e.target.checked)}
                        />
                        <span>Show password characters</span>
                      </label>
                    </div>

                    {/* Password Policy Requirements */}
                    <div className="fb-policy-checklist" style={{
                      background: 'rgba(22, 27, 34, 0.8)',
                      border: '1px solid #30363d',
                      borderRadius: '8px',
                      padding: '0.8rem',
                      margin: '0.75rem 0'
                    }}>
                      <div className="fb-policy-title" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#8b949e', marginBottom: '0.5rem' }}>
                        Password Policy Requirements:
                      </div>
                      <div className="fb-policy-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.35rem' }}>
                        <div className={`fb-policy-item ${policyChecks.length ? 'met' : ''}`} style={{ fontSize: '0.8rem', color: policyChecks.length ? '#3fb950' : '#8b949e' }}>
                          <span>{policyChecks.length ? '✓' : '○'}</span> At least 8 characters
                        </div>
                        <div className={`fb-policy-item ${policyChecks.upper ? 'met' : ''}`} style={{ fontSize: '0.8rem', color: policyChecks.upper ? '#3fb950' : '#8b949e' }}>
                          <span>{policyChecks.upper ? '✓' : '○'}</span> Uppercase letter (A-Z)
                        </div>
                        <div className={`fb-policy-item ${policyChecks.lower ? 'met' : ''}`} style={{ fontSize: '0.8rem', color: policyChecks.lower ? '#3fb950' : '#8b949e' }}>
                          <span>{policyChecks.lower ? '✓' : '○'}</span> Lowercase letter (a-z)
                        </div>
                        <div className={`fb-policy-item ${policyChecks.number ? 'met' : ''}`} style={{ fontSize: '0.8rem', color: policyChecks.number ? '#3fb950' : '#8b949e' }}>
                          <span>{policyChecks.number ? '✓' : '○'}</span> Number (0-9)
                        </div>
                        <div className={`fb-policy-item ${policyChecks.special ? 'met' : ''}`} style={{ fontSize: '0.8rem', color: policyChecks.special ? '#3fb950' : '#8b949e' }}>
                          <span>{policyChecks.special ? '✓' : '○'}</span> Special character (!@#$...)
                        </div>
                        <div className={`fb-policy-item ${policyChecks.match ? 'met' : ''}`} style={{ fontSize: '0.8rem', color: policyChecks.match ? '#3fb950' : '#8b949e' }}>
                          <span>{policyChecks.match ? '✓' : '○'}</span> Passwords match
                        </div>
                      </div>
                    </div>

                    <div className="fb-reset-btn-row" style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '0.6rem' }}>
                      <button
                        type="button"
                        className="fb-btn-close-reset"
                        onClick={() => setShowForgotWizard(false)}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="fb-btn-perform-reset"
                        disabled={tokenResetLoading || !isPolicyValid}
                        id="reset-password-btn"
                      >
                        {tokenResetLoading ? 'Updating Password…' : 'Reset Password'}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* STEP 4: Password Reset Successful */}
              {wizardStep === 'success' && (
                <div className="fb-wizard-content fb-sent-content" style={{ textAlign: 'center', padding: '1rem 0' }}>
                  <div className="fb-sent-badge-wrap success" style={{
                    width: '54px',
                    height: '54px',
                    borderRadius: '50%',
                    background: 'rgba(46, 160, 67, 0.15)',
                    border: '2px solid #2ea043',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 1rem auto',
                    fontSize: '1.6rem',
                    color: '#3fb950'
                  }}>
                    ✓
                  </div>
                  <h4 className="fb-sent-title" style={{ color: '#f0f6fc', margin: '0 0 0.5rem 0', fontSize: '1.2rem' }}>
                    Password Reset Successful
                  </h4>
                  <p className="fb-sent-msg" style={{ color: '#c9d1d9', fontSize: '0.92rem', maxWidth: '420px', margin: '0 auto 1.5rem auto', lineHeight: '1.5' }}>
                    {successNotice || 'Password reset successful. Please log in with your new password.'}
                  </p>

                  <div className="fb-reset-btn-row" style={{ justifyContent: 'center' }}>
                    <button
                      type="button"
                      className="fb-btn-perform-reset"
                      onClick={() => setShowForgotWizard(false)}
                      style={{ minWidth: '180px' }}
                    >
                      Proceed to Log In
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
