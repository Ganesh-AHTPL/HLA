import { create } from 'zustand';

export const useWorkspaceStore = create((set) => ({
  // User & Auth
  currentUser: (() => {
    try {
      const saved = localStorage.getItem('hla_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  })(),
  setCurrentUser: (user) => {
    if (user) {
      localStorage.setItem('hla_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('hla_user');
    }
    set({ currentUser: user });
  },

  // Active Project & Document selection
  activeView: 'workspaces', // 'workspaces' | 'project-studio'
  setActiveView: (view) => set({ activeView: view }),

  activeProject: null,
  setActiveProject: (project) => set({ activeProject: project }),

  selectedDocId: null,
  setSelectedDocId: (docId) => set({ selectedDocId: docId }),

  projectStudioTab: 'analysis', // 'analysis' | 'files' | 'db-connectors'
  setProjectStudioTab: (tab) => set({ projectStudioTab: tab }),

  // Theme
  theme: localStorage.getItem('hla_theme') || 'light',
  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('hla_theme', theme);
    set({ theme });
  },
  toggleTheme: () =>
    set((state) => {
      const newTheme = state.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('hla_theme', newTheme);
      return { theme: newTheme };
    }),

  // Modals
  modals: {
    login: false,
    userMgmt: false,
    rules: false,
    introspect: false,
    roleInfo: false,
    schedule: false,
  },
  openModal: (modalName) =>
    set((state) => ({
      modals: { ...state.modals, [modalName]: true },
    })),
  closeModal: (modalName) =>
    set((state) => ({
      modals: { ...state.modals, [modalName]: false },
    })),
  setModals: (modalState) =>
    set((state) => ({
      modals: { ...state.modals, ...modalState },
    })),
}));
