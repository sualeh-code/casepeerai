import React from 'react';
import { LayoutDashboard, Settings, FileText, Terminal, Zap, Brain, DollarSign, LogOut, Phone } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'cases', label: 'Cases', icon: FileText },
    { id: 'n8n', label: 'n8n Executions', icon: Zap },
    { id: 'openai', label: 'OpenAI Usage', icon: Brain },
    { id: 'vapi', label: 'VAPI Calls', icon: Phone },
    { id: 'costs', label: 'Costs', icon: DollarSign },
    { id: 'settings', label: 'Settings', icon: Settings },
    { id: 'logs', label: 'System Logs', icon: Terminal },
];

const DashboardLayout = ({ children, activeTab, onTabChange }) => {
    const handleLogout = () => {
        sessionStorage.removeItem('dashboard_auth');
        window.location.reload();
    };

    return (
        <div className="min-h-screen bg-background text-foreground flex">
            {/* Sidebar */}
            <aside className="w-64 border-r bg-card flex flex-col">
                <div className="p-6">
                    <h1 className="text-2xl font-bold tracking-tight">CasePeer AI</h1>
                </div>
                <nav className="space-y-1 px-4 flex-1">
                    {navItems.map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => onTabChange(id)}
                            className={cn(
                                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                                activeTab === id
                                    ? "bg-primary text-primary-foreground"
                                    : "hover:bg-muted text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <Icon className="h-4 w-4" />
                            {label}
                        </button>
                    ))}
                </nav>
                <div className="p-4 border-t">
                    <button
                        onClick={handleLogout}
                        className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    >
                        <LogOut className="h-4 w-4" />
                        Logout
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-auto p-8">
                {children}
            </main>
        </div>
    );
};

export default DashboardLayout;
