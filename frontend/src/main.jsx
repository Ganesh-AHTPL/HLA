import React from 'react'
import ReactDOM from 'react-dom/client'
import axios from 'axios'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './services/queryClient'
import App from './App.jsx'
import './index.css'

// Synchronously configure Authorization header from saved token before initial render
const savedToken = localStorage.getItem('access_token') || localStorage.getItem('hla_token')
if (savedToken) {
  axios.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
