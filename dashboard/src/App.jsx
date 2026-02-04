import React, { useState } from 'react';
import DashboardLayout from './components/DashboardLayout';
import StatsOverview from './components/StatsOverview';
import CaseTable from './components/CaseTable';
import SettingsForm from './components/SettingsForm';
import SystemLogs from './components/SystemLogs';
import CaseDetails from './components/CaseDetails';
import CostDashboard from './components/CostDashboard';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedCaseId, setSelectedCaseId] = useState(null);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab !== 'cases') {
      setSelectedCaseId(null);
    }
  };

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
      {activeTab === 'settings' && <SettingsForm />}
      {activeTab === 'logs' && <SystemLogs />}
      {activeTab === 'costs' && <CostDashboard />}
    </DashboardLayout>
  );
}

export default App;
