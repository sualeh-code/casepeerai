import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Phone, Mail, CheckCircle, XCircle, Clock, RefreshCw, ChevronDown, ChevronUp, Loader2, AlertTriangle, PhoneCall, Calendar } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';

const COLORS = ['#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#6366f1', '#ec4899', '#14b8a6'];

const statusColors = {
    queued: 'bg-gray-100 text-gray-800',
    scheduled: 'bg-purple-100 text-purple-800',
    ringing: 'bg-yellow-100 text-yellow-800',
    in_progress: 'bg-blue-100 text-blue-800',
    ended: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    no_answer: 'bg-orange-100 text-orange-800',
    voicemail: 'bg-amber-100 text-amber-800',
    needs_manual: 'bg-red-200 text-red-900',
};

const emailStatusColors = {
    pending: 'bg-yellow-100 text-yellow-800',
    confirmed: 'bg-green-100 text-green-800',
    new_email: 'bg-blue-100 text-blue-800',
    not_obtained: 'bg-red-100 text-red-800',
};

function formatLabel(str) {
    if (!str || str === '-') return str;
    return str.replace(/([A-Z])/g, ' $1').replace(/[-_]/g, ' ').replace(/\b\w/g, l => l.toUpperCase()).trim();
}

// ─── Analytics Sub-Tab ───────────────────────────────────────────────
const AnalyticsTab = () => {
    const [callData, setCallData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/internal-api/integrations/vapi/calls');
                if (res.ok) {
                    const data = await res.json();
                    if (data.error) setError(data.error);
                    else setCallData(data);
                } else if (res.status === 400) {
                    setError("VAPI API Key not configured. Go to Settings to add it.");
                } else {
                    setError("Failed to fetch VAPI data");
                }
            } catch (err) {
                setError("Failed to connect to VAPI API");
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    if (loading) return <div className="p-8 text-muted-foreground">Loading analytics...</div>;
    if (error) return <Card><CardContent className="p-6"><div className="text-muted-foreground">{error}</div></CardContent></Card>;

    const statusData = callData?.status_breakdown
        ? Object.entries(callData.status_breakdown).map(([name, value]) => ({ name, value }))
        : [];
    const typeData = callData?.type_breakdown
        ? Object.entries(callData.type_breakdown).map(([name, value]) => ({ name: formatLabel(name), value }))
        : [];
    const endReasonData = callData?.end_reasons
        ? Object.entries(callData.end_reasons).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([name, value]) => ({ name: formatLabel(name), value }))
        : [];
    const recentCostData = callData?.recent_calls
        ? callData.recent_calls.filter(c => c.cost > 0).map(c => ({
            name: c.id.substring(0, 8),
            cost: parseFloat((c.cost || 0).toFixed(4)),
            duration: Math.round((c.duration || 0) / 60 * 10) / 10,
        }))
        : [];

    return (
        <div className="space-y-4">
            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total VAPI Calls</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{callData?.total_calls || 0}</div>
                        <p className="text-xs text-muted-foreground">{callData?.in_progress_count || 0} in progress</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">${callData?.total_cost?.toFixed(2) || '0.00'}</div>
                        <p className="text-xs text-muted-foreground">${callData?.avg_cost_per_call?.toFixed(4) || '0'} avg/call</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Duration</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{callData?.total_duration_minutes?.toFixed(1) || 0} min</div>
                        <p className="text-xs text-muted-foreground">{callData?.avg_duration_seconds?.toFixed(0) || 0}s avg/call</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Cost/Minute</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            ${callData?.total_duration_minutes > 0
                                ? (callData.total_cost / callData.total_duration_minutes).toFixed(4)
                                : '0.00'}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Charts */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Cost per Call (Recent)</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[280px] w-full">
                            {recentCostData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={recentCostData}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="name" />
                                        <YAxis />
                                        <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))' }}
                                            formatter={(value, name) => [name === 'cost' ? `$${value}` : `${value} min`, name === 'cost' ? 'Cost' : 'Duration']} />
                                        <Bar dataKey="cost" fill="#8b5cf6" name="Cost ($)" />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : <div className="h-full flex items-center justify-center text-muted-foreground">No cost data</div>}
                        </div>
                    </CardContent>
                </Card>
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Call Types</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[280px] w-full">
                            {typeData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={typeData} cx="50%" cy="50%" innerRadius={55} outerRadius={75} paddingAngle={5} dataKey="value">
                                            {typeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                                        </Pie>
                                        <Tooltip /><Legend />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : <div className="h-full flex items-center justify-center text-muted-foreground">No data</div>}
                        </div>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Call End Reasons</CardTitle>
                        <CardDescription>Why calls ended (top 8)</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[280px] w-full">
                            {endReasonData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={endReasonData} layout="vertical">
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis type="number" />
                                        <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
                                        <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))' }} />
                                        <Bar dataKey="value" fill="#06b6d4" name="Count" />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : <div className="h-full flex items-center justify-center text-muted-foreground">No data</div>}
                        </div>
                    </CardContent>
                </Card>
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Call Status</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[280px] w-full">
                            {statusData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={statusData} cx="50%" cy="50%" innerRadius={55} outerRadius={75} paddingAngle={5} dataKey="value">
                                            {statusData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                                        </Pie>
                                        <Tooltip /><Legend />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : <div className="h-full flex items-center justify-center text-muted-foreground">No data</div>}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Recent Calls Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent VAPI Calls</CardTitle>
                    <CardDescription>Raw call data from VAPI API</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="border rounded-md overflow-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-muted">
                                    <th className="p-3 text-left font-medium">ID</th>
                                    <th className="p-3 text-left font-medium">Type</th>
                                    <th className="p-3 text-left font-medium">Status</th>
                                    <th className="p-3 text-right font-medium">Cost</th>
                                    <th className="p-3 text-right font-medium">Duration</th>
                                    <th className="p-3 text-left font-medium">End Reason</th>
                                    <th className="p-3 text-left font-medium">Started</th>
                                </tr>
                            </thead>
                            <tbody>
                                {callData?.recent_calls?.length > 0 ? callData.recent_calls.map((call) => (
                                    <tr key={call.id} className="border-t hover:bg-muted/50">
                                        <td className="p-3 font-mono text-xs">{call.id.substring(0, 12)}...</td>
                                        <td className="p-3">{formatLabel(call.type)}</td>
                                        <td className="p-3">
                                            <span className={call.status === 'ended' ? 'text-green-600 font-medium' : call.status === 'in-progress' ? 'text-blue-600 font-medium' : 'text-muted-foreground'}>
                                                {call.status}
                                            </span>
                                        </td>
                                        <td className="p-3 text-right font-mono">${(call.cost || 0).toFixed(4)}</td>
                                        <td className="p-3 text-right">{call.duration ? `${Math.round(call.duration)}s` : '-'}</td>
                                        <td className="p-3 text-xs">{formatLabel(call.endedReason || '-')}</td>
                                        <td className="p-3 text-xs text-muted-foreground">{call.startedAt ? new Date(call.startedAt).toLocaleString() : '-'}</td>
                                    </tr>
                                )) : <tr><td colSpan={7} className="p-4 text-center text-muted-foreground">No calls found</td></tr>}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Cost Breakdown */}
            {callData?.recent_calls?.some(c => c.costBreakdown && Object.keys(c.costBreakdown).length > 0) && (
                <Card>
                    <CardHeader>
                        <CardTitle>Cost Breakdown (Latest Call)</CardTitle>
                    </CardHeader>
                    <CardContent>
                        {(() => {
                            const latestWithCost = callData.recent_calls.find(c => c.costBreakdown && Object.keys(c.costBreakdown).length > 0);
                            if (!latestWithCost) return null;
                            const entries = Object.entries(latestWithCost.costBreakdown).filter(([, v]) => typeof v === 'number');
                            return (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    {entries.map(([key, value]) => (
                                        <div key={key} className="p-3 border rounded-lg">
                                            <div className="text-xs font-medium text-muted-foreground capitalize">{formatLabel(key)}</div>
                                            <div className="text-lg font-bold">
                                                {key.includes('Token') || key.includes('Characters') ? value.toLocaleString() : `$${value.toFixed(4)}`}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            );
                        })()}
                    </CardContent>
                </Card>
            )}
        </div>
    );
};

// ─── Main Component ──────────────────────────────────────────────────
const ProviderCalls = () => {
    const [calls, setCalls] = useState([]);
    const [kpi, setKpi] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [expandedRow, setExpandedRow] = useState(null);
    const [caseFilter, setCaseFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [emailFilter, setEmailFilter] = useState('');
    const [triggerCaseId, setTriggerCaseId] = useState('');
    const [triggering, setTriggering] = useState(false);
    const [actionLoading, setActionLoading] = useState(null);

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            const params = new URLSearchParams();
            if (caseFilter) params.set('case_id', caseFilter);
            if (statusFilter) params.set('status', statusFilter);
            if (emailFilter) params.set('email_status', emailFilter);
            params.set('limit', '200');
            const res = await fetch(`/internal-api/provider-calls?${params}`);
            if (res.ok) {
                const data = await res.json();
                setCalls(data.calls || []);
                setKpi(data.kpi || {});
                setError(null);
            } else { setError('Failed to fetch provider calls'); }
        } catch (err) { setError(err.message); }
        finally { setLoading(false); }
    }, [caseFilter, statusFilter, emailFilter]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleTrigger = async () => {
        if (!triggerCaseId.trim()) return;
        setTriggering(true);
        try {
            const res = await fetch(`/internal-api/provider-calls/${triggerCaseId.trim()}/trigger`, { method: 'POST' });
            if (res.ok) setTimeout(fetchData, 2000);
        } catch (err) { console.error('Trigger failed:', err); }
        finally { setTriggering(false); }
    };

    const handleRetry = async (callId) => {
        setActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/retry`, { method: 'POST' });
            setTimeout(fetchData, 2000);
        } catch (err) { console.error('Retry failed:', err); }
        finally { setActionLoading(null); }
    };

    const handleSchedule = async (callId) => {
        const time = prompt('Schedule call for (ISO datetime or relative like "3pm", "tomorrow 10am"):');
        if (!time) return;
        setActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/schedule`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scheduled_at: time }),
            });
            setTimeout(fetchData, 1000);
        } catch (err) { console.error('Schedule failed:', err); }
        finally { setActionLoading(null); }
    };

    const handleManualEmail = async (callId) => {
        const email = prompt('Enter confirmed email address for this provider:');
        if (!email || !email.includes('@')) return;
        setActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/manual-email`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            setTimeout(fetchData, 1000);
        } catch (err) { console.error('Manual email failed:', err); }
        finally { setActionLoading(null); }
    };

    const uniqueCases = [...new Set(calls.map(c => c.case_id).filter(Boolean))];

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Provider Calls</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        AI phone calls to providers to confirm or obtain email addresses for negotiations.
                    </p>
                </div>
                <button onClick={fetchData}
                    className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted transition-colors">
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
                </button>
            </div>

            <Tabs defaultValue="calls" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="calls">Call Records</TabsTrigger>
                    <TabsTrigger value="analytics">VAPI Analytics</TabsTrigger>
                </TabsList>

                {/* ── Call Records Tab ── */}
                <TabsContent value="calls" className="space-y-4">
                    {error && (
                        <Card><CardContent className="p-4">
                            <div className="text-red-600 flex items-center gap-2"><AlertTriangle className="h-4 w-4" />{error}</div>
                        </CardContent></Card>
                    )}

                    {/* KPI Cards */}
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Calls</CardTitle>
                                <PhoneCall className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent><div className="text-2xl font-bold">{kpi.total_calls || 0}</div></CardContent>
                        </Card>
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Emails Confirmed</CardTitle>
                                <CheckCircle className="h-4 w-4 text-green-600" />
                            </CardHeader>
                            <CardContent><div className="text-2xl font-bold text-green-600">{kpi.emails_confirmed || 0}</div></CardContent>
                        </Card>
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Pending</CardTitle>
                                <Clock className="h-4 w-4 text-yellow-600" />
                            </CardHeader>
                            <CardContent><div className="text-2xl font-bold text-yellow-600">{kpi.emails_pending || 0}</div></CardContent>
                        </Card>
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Failed</CardTitle>
                                <XCircle className="h-4 w-4 text-red-600" />
                            </CardHeader>
                            <CardContent><div className="text-2xl font-bold text-red-600">{kpi.calls_failed || 0}</div></CardContent>
                        </Card>
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
                                <Phone className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent><div className="text-2xl font-bold">${(kpi.total_cost || 0).toFixed(2)}</div></CardContent>
                        </Card>
                    </div>

                    {/* Trigger + Filters */}
                    <Card>
                        <CardContent className="p-4">
                            <div className="flex flex-wrap gap-4 items-end">
                                <div className="flex-shrink-0">
                                    <label className="text-xs font-medium text-muted-foreground block mb-1">Trigger Calls for Case</label>
                                    <div className="flex gap-2">
                                        <input type="text" placeholder="Case ID" value={triggerCaseId}
                                            onChange={(e) => setTriggerCaseId(e.target.value)}
                                            className="rounded-md border px-3 py-1.5 text-sm w-28 bg-background" />
                                        <button onClick={handleTrigger} disabled={triggering || !triggerCaseId.trim()}
                                            className="inline-flex items-center gap-1 rounded-md bg-primary text-primary-foreground px-3 py-1.5 text-sm font-medium hover:bg-primary/90 disabled:opacity-50">
                                            {triggering ? <Loader2 className="h-3 w-3 animate-spin" /> : <PhoneCall className="h-3 w-3" />}
                                            Call Providers
                                        </button>
                                    </div>
                                </div>
                                <div className="h-8 w-px bg-border" />
                                <div>
                                    <label className="text-xs font-medium text-muted-foreground block mb-1">Case</label>
                                    <select value={caseFilter} onChange={(e) => setCaseFilter(e.target.value)}
                                        className="rounded-md border px-2 py-1.5 text-sm bg-background">
                                        <option value="">All Cases</option>
                                        {uniqueCases.map(id => <option key={id} value={id}>{id}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-muted-foreground block mb-1">Status</label>
                                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                                        className="rounded-md border px-2 py-1.5 text-sm bg-background">
                                        <option value="">All</option>
                                        <option value="queued">Queued</option>
                                        <option value="scheduled">Scheduled</option>
                                        <option value="ringing">Ringing</option>
                                        <option value="in_progress">In Progress</option>
                                        <option value="ended">Ended</option>
                                        <option value="failed">Failed</option>
                                        <option value="no_answer">No Answer</option>
                                        <option value="needs_manual">Needs Manual</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-muted-foreground block mb-1">Email Status</label>
                                    <select value={emailFilter} onChange={(e) => setEmailFilter(e.target.value)}
                                        className="rounded-md border px-2 py-1.5 text-sm bg-background">
                                        <option value="">All</option>
                                        <option value="pending">Pending</option>
                                        <option value="confirmed">Confirmed</option>
                                        <option value="new_email">New Email</option>
                                        <option value="not_obtained">Not Obtained</option>
                                    </select>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Calls Table */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Call Records</CardTitle>
                            <CardDescription>{calls.length} call(s) found. Click a row to expand details.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="border rounded-md overflow-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-muted">
                                            <th className="p-3 text-left font-medium">Provider</th>
                                            <th className="p-3 text-left font-medium">Case</th>
                                            <th className="p-3 text-left font-medium">Phone</th>
                                            <th className="p-3 text-left font-medium">Email on File</th>
                                            <th className="p-3 text-left font-medium">Confirmed Email</th>
                                            <th className="p-3 text-center font-medium">Status</th>
                                            <th className="p-3 text-center font-medium">Email</th>
                                            <th className="p-3 text-center font-medium">Attempt</th>
                                            <th className="p-3 text-left font-medium">Type</th>
                                            <th className="p-3 text-left font-medium">Created</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {calls.length === 0 ? (
                                            <tr><td colSpan={10} className="p-8 text-center text-muted-foreground">
                                                No calls found. Trigger calls for a case above.
                                            </td></tr>
                                        ) : calls.map((call) => (
                                            <React.Fragment key={call.id}>
                                                <tr className="border-t hover:bg-muted/50 cursor-pointer"
                                                    onClick={() => setExpandedRow(expandedRow === call.id ? null : call.id)}>
                                                    <td className="p-3 font-medium">{call.provider_name}</td>
                                                    <td className="p-3 font-mono text-xs">{call.case_id}</td>
                                                    <td className="p-3 text-xs">{call.provider_phone || '-'}</td>
                                                    <td className="p-3 text-xs">{call.existing_email || '-'}</td>
                                                    <td className="p-3 text-xs font-medium">
                                                        {call.confirmed_email ? <span className="text-green-600">{call.confirmed_email}</span> : '-'}
                                                    </td>
                                                    <td className="p-3 text-center">
                                                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[call.status] || 'bg-gray-100'}`}>
                                                            {call.status?.replace('_', ' ')}
                                                        </span>
                                                    </td>
                                                    <td className="p-3 text-center">
                                                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${emailStatusColors[call.email_status] || 'bg-gray-100'}`}>
                                                            {call.email_status?.replace('_', ' ')}
                                                        </span>
                                                    </td>
                                                    <td className="p-3 text-center">{call.attempt_number || 1}</td>
                                                    <td className="p-3 text-xs">{call.call_type?.replace('_', ' ')}</td>
                                                    <td className="p-3 text-xs text-muted-foreground">
                                                        {call.created_at ? new Date(call.created_at + 'Z').toLocaleString() : '-'}
                                                    </td>
                                                </tr>

                                                {expandedRow === call.id && (
                                                    <tr>
                                                        <td colSpan={10} className="bg-muted/30 p-4 border-t">
                                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <div>
                                                                    <h4 className="font-medium mb-2 text-sm">Transcript</h4>
                                                                    <pre className="text-xs whitespace-pre-wrap max-h-48 overflow-y-auto bg-background p-3 rounded border">
                                                                        {call.transcript || 'No transcript available'}
                                                                    </pre>
                                                                </div>
                                                                <div>
                                                                    <h4 className="font-medium mb-2 text-sm">AI Summary</h4>
                                                                    <p className="text-sm mb-4">{call.summary || 'No summary'}</p>
                                                                    {call.recording_url && (
                                                                        <div className="mb-4">
                                                                            <h4 className="font-medium mb-2 text-sm">Recording</h4>
                                                                            <audio controls src={call.recording_url} className="w-full" />
                                                                        </div>
                                                                    )}
                                                                    <div className="grid grid-cols-2 gap-2 text-sm">
                                                                        <div className="text-muted-foreground">Duration</div>
                                                                        <div>{call.call_duration_seconds ? `${Math.round(call.call_duration_seconds)}s` : '-'}</div>
                                                                        <div className="text-muted-foreground">Cost</div>
                                                                        <div>{call.call_cost ? `$${call.call_cost.toFixed(4)}` : '-'}</div>
                                                                        <div className="text-muted-foreground">End Reason</div>
                                                                        <div>{call.end_reason || '-'}</div>
                                                                        <div className="text-muted-foreground">Vapi Call ID</div>
                                                                        <div className="font-mono text-xs">{call.vapi_call_id ? call.vapi_call_id.substring(0, 16) + '...' : '-'}</div>
                                                                        {call.scheduled_at && <>
                                                                            <div className="text-muted-foreground">Scheduled At</div>
                                                                            <div>{new Date(call.scheduled_at).toLocaleString()}</div>
                                                                        </>}
                                                                        {call.redirect_number && <>
                                                                            <div className="text-muted-foreground">Redirect #</div>
                                                                            <div>{call.redirect_number}</div>
                                                                        </>}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <div className="flex gap-2 mt-4 pt-3 border-t">
                                                                <button onClick={(e) => { e.stopPropagation(); handleRetry(call.id); }}
                                                                    disabled={actionLoading === call.id}
                                                                    className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50">
                                                                    {actionLoading === call.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                                                                    Retry Call
                                                                </button>
                                                                <button onClick={(e) => { e.stopPropagation(); handleSchedule(call.id); }}
                                                                    className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted">
                                                                    <Calendar className="h-3 w-3" /> Schedule
                                                                </button>
                                                                {call.email_status !== 'confirmed' && call.email_status !== 'new_email' && (
                                                                    <button onClick={(e) => { e.stopPropagation(); handleManualEmail(call.id); }}
                                                                        disabled={actionLoading === call.id}
                                                                        className="inline-flex items-center gap-1 rounded-md bg-blue-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-blue-700 disabled:opacity-50">
                                                                        <Mail className="h-3 w-3" /> Enter Email
                                                                    </button>
                                                                )}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )}
                                            </React.Fragment>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* ── Analytics Tab ── */}
                <TabsContent value="analytics">
                    <AnalyticsTab />
                </TabsContent>
            </Tabs>
        </div>
    );
};

export default ProviderCalls;
