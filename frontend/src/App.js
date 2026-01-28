import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

// Placeholder components - to be implemented
const Login = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">Login Page</div>;
const Dashboard = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">Dashboard</div>;
const StrategyLab = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">AI Strategy Lab</div>;
const LiveTrading = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">Live Trading</div>;
const AIChat = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">AI Chat</div>;
const Alerts = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">Alerts & Activity</div>;
const Settings = () => <div className="flex items-center justify-center h-screen bg-gray-900 text-white">Settings</div>;

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-900">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/strategy-lab" element={<StrategyLab />} />
          <Route path="/live-trading" element={<LiveTrading />} />
          <Route path="/ai-chat" element={<AIChat />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
