import React from 'react';
import { LayoutDashboard, Settings, FileText, Terminal, DollarSign, LogOut, Play, PhoneCall } from 'lucide-react';
import { cn } from '@/lib/utils';

const navSections = [
    {
        label: 'Main',
        items: [
            { id: 'dashboard', label: 'Dashboard', desc: 'Overview stats & charts', icon: LayoutDashboard },
            { id: 'cases', label: 'Cases', desc: 'All cases & details', icon: FileText },
        ],
    },
    {
        label: 'Operations',
        items: [
            { id: 'automations', label: 'Automations', desc: 'Scheduled workflows', icon: Play },
            { id: 'provider-calls', label: 'Provider Calls', desc: 'Phone calls & VAPI', icon: PhoneCall },
        ],
    },
    {
        label: 'Monitoring',
        items: [
            { id: 'costs', label: 'Usage & Costs', desc: 'OpenAI, n8n, tokens', icon: DollarSign },
            { id: 'logs', label: 'System Logs', desc: 'Live server output', icon: Terminal },
        ],
    },
    {
        label: 'Admin',
        items: [
            { id: 'settings', label: 'Settings', desc: 'API keys & config', icon: Settings },
        ],
    },
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
                    <p className="text-xs text-muted-foreground mt-1">Beverly Law Firm</p>
                </div>
                <nav className="flex-1 px-4 space-y-4 overflow-y-auto">
                    {navSections.map((section) => (
                        <div key={section.label}>
                            <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                                {section.label}
                            </div>
                            <div className="space-y-0.5">
                                {section.items.map(({ id, label, desc, icon: Icon }) => (
                                    <button
                                        key={id}
                                        onClick={() => onTabChange(id)}
                                        className={cn(
                                            "flex w-full items-start gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                                            activeTab === id
                                                ? "bg-primary text-primary-foreground"
                                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                                        )}
                                    >
                                        <Icon className="h-4 w-4 mt-0.5 shrink-0" />
                                        <div className="text-left">
                                            <div>{label}</div>
                                            <div className={cn(
                                                "text-[10px] font-normal leading-tight",
                                                activeTab === id ? "text-primary-foreground/70" : "text-muted-foreground/60"
                                            )}>{desc}</div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>
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
