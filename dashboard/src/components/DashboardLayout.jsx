import React, { useState } from 'react';
import { LayoutDashboard, Settings, FileText, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';

const DashboardLayout = ({ children, activeTab, onTabChange }) => {
    return (
        <div className="min-h-screen bg-background text-foreground flex">
            {/* Sidebar */}
            <aside className="w-64 border-r bg-card">
                <div className="p-6">
                    <h1 className="text-2xl font-bold tracking-tight">CasePeer AI</h1>
                </div>
                <nav className="space-y-1 px-4">
                    <button
                        onClick={() => onTabChange('dashboard')}
                        className={cn(
                            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            activeTab === 'dashboard'
                                ? "bg-primary text-primary-foreground"
                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <LayoutDashboard className="h-4 w-4" />
                        Dashboard
                    </button>
                    <button
                        onClick={() => onTabChange('cases')}
                        className={cn(
                            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            activeTab === 'cases'
                                ? "bg-primary text-primary-foreground"
                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <FileText className="h-4 w-4" />
                        Cases
                    </button>
                    <button
                        onClick={() => onTabChange('settings')}
                        className={cn(
                            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            activeTab === 'settings'
                                ? "bg-primary text-primary-foreground"
                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <Settings className="h-4 w-4" />
                        Settings
                    </button>
                    <button
                        onClick={() => onTabChange('logs')}
                        className={cn(
                            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            activeTab === 'logs'
                                ? "bg-primary text-primary-foreground"
                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <Terminal className="h-4 w-4" />
                        System Logs
                    </button>
                    <button
                        onClick={() => onTabChange('costs')}
                        className={cn(
                            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                            activeTab === 'costs'
                                ? "bg-primary text-primary-foreground"
                                : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <span className="h-4 w-4 font-bold text-center">$</span>
                        Costs
                    </button>
                </nav>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-auto p-8">
                {children}
            </main>
        </div>
    );
};

export default DashboardLayout;
