import React, { useState } from 'react';
import DashboardLayout from './components/DashboardLayout';
import StatsOverview from './components/StatsOverview';
import CaseTable from './components/CaseTable';
import SettingsForm from './components/SettingsForm';
import SystemLogs from './components/SystemLogs';
import CaseDetails from './components/CaseDetails';
import CostDashboard from './components/CostDashboard';
import N8nExecutions from './components/N8nExecutions';
import OpenAiUsage from './components/OpenAiUsage';
import LoginPage from './components/LoginPage';

function App() {
  const [authenticated, setAuthenticated] = useState(
    () => sessionStorage.getItem('dashboard_auth') === 'true'
  );
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedCaseId, setSelectedCaseId] = useState(null);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab !== 'cases') {
      setSelectedCaseId(null);
    }
  };

  if (!authenticated) {
    return <LoginPage onLogin={() => setAuthenticated(true)} />;
  }

  return (
    <DashboardLayout activeTab={activeTab} onTabChange={handleTabChange}>
      {activeTab === 'dashboard' && <StatsOverview />}
      {activeTab === 'cases' && (
        selectedCaseId ? (
          <CaseDetails caseId={selectedCaseId} onBack={() => setSelectedCaseId(null)} />
        ) : (
          <CaseTable onCaseSelect={setSelectedCaseId} />
        )
      )}
      {activeTab === 'n8n' && <N8nExecutions />}
      {activeTab === 'openai' && <OpenAiUsage />}
      {activeTab === 'costs' && <CostDashboard />}
      {activeTab === 'settings' && <SettingsForm />}
      {activeTab === 'logs' && <SystemLogs />}
    </DashboardLayout>
  );
}

export default App;
