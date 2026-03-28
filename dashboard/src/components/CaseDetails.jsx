
import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, FileText, Bell, Bot, Trash2, Mail, DollarSign, Phone, Loader2, CheckCircle, XCircle, Zap, Eye, RefreshCw, StickyNote, ChevronDown, ChevronUp, PhoneCall, Calendar, AlertTriangle } from 'lucide-react';
import CaseNotes from './CaseNotes';
import AgentActivity from './AgentActivity';

const callStatusColors = {
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

const CASE_WORKFLOWS = [
    { id: 'initial_negotiation', name: 'Send Initial Offers', icon: Mail, description: 'Email all providers with initial negotiation offers', endpoint: (caseId) => `/internal-api/workflows/initial-negotiation/${caseId}` },
    { id: 'classification', name: 'Classify Documents', icon: FileText, description: 'AI classify all case documents', endpoint: (caseId) => `/internal-api/workflows/classification/${caseId}` },
    { id: 'thirdparty', name: 'Third-Party Settlement', icon: DollarSign, description: 'Process defendant insurance settlement', endpoint: (caseId) => `/internal-api/workflows/thirdparty/${caseId}` },
    { id: 'get_mail_sub', name: 'Get Provider Emails (Legacy)', icon: Phone, description: 'Phone providers to get email addresses (polling)', endpoint: (caseId) => `/internal-api/workflows/get-mail-sub/${caseId}` },
    { id: 'provider_calls', name: 'Call Providers for Emails', icon: Phone, description: 'Call all providers to confirm/get email addresses (webhook)', endpoint: (caseId) => `/internal-api/provider-calls/${caseId}/trigger` },
];

const CaseDetails = ({ caseId, onBack }) => {
    const [caseData, setCaseData] = useState(null);
    const [classifications, setClassifications] = useState([]);
    const [reminders, setReminders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [runningWorkflow, setRunningWorkflow] = useState(null);
    const [workflowResult, setWorkflowResult] = useState(null);
    const [liveData, setLiveData] = useState(null);
    const [liveDataType, setLiveDataType] = useState(null);
    const [loadingLive, setLoadingLive] = useState(null);
    const [noteText, setNoteText] = useState('');
    const [addingNote, setAddingNote] = useState(false);
    const [showNoteInput, setShowNoteInput] = useState(false);
    const [refreshingStats, setRefreshingStats] = useState(false);
    const [providerCalls, setProviderCalls] = useState([]);
    const [expandedProvider, setExpandedProvider] = useState(null);
    const [callActionLoading, setCallActionLoading] = useState(null);

    const fetchProviderCalls = async () => {
        try {
            const res = await fetch(`/internal-api/provider-calls/${caseId}`);
            if (res.ok) {
                const data = await res.json();
                setProviderCalls(data.calls || []);
            }
        } catch (err) {
            console.error("Error fetching provider calls:", err);
        }
    };

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const caseRes = await fetch(`/internal-api/cases/${caseId}`);
                if (caseRes.ok) setCaseData(await caseRes.json());

                const [classRes, remRes] = await Promise.all([
                    fetch(`/internal-api/classifications?case_id=${caseId}`),
                    fetch(`/internal-api/cases/${caseId}/reminders`)
                ]);

                if (classRes.ok) setClassifications(await classRes.json());
                if (remRes.ok) setReminders(await remRes.json());

                // Auto-fetch treatment data and provider calls
                try {
                    const treatRes = await fetch(`/internal-api/cases/${caseId}/live/treatment`);
                    if (treatRes.ok) {
                        setLiveData(await treatRes.json());
                        setLiveDataType('treatment');
                    }
                } catch (e) { /* non-critical */ }

                await fetchProviderCalls();
            } catch (error) {
                console.error("Error fetching case details:", error);
            } finally {
                setLoading(false);
            }
        };

        if (caseId) fetchData();
    }, [caseId]);

    const fetchLiveData = async (type) => {
        setLoadingLive(type);
        setLiveDataType(type);
        try {
            const endpoint = type === 'treatment'
                ? `/internal-api/cases/${caseId}/live/treatment`
                : `/internal-api/cases/${caseId}/live/settlement`;
            const res = await fetch(endpoint);
            if (res.ok) setLiveData(await res.json());
            else setLiveData({ error: 'Failed to fetch' });
            if (type === 'treatment') fetchProviderCalls();
        } catch (err) { setLiveData({ error: err.message }); }
        finally { setLoadingLive(null); }
    };

    const addNote = async () => {
        if (!noteText.trim()) return;
        setAddingNote(true);
        try {
            const res = await fetch(`/internal-api/cases/${caseId}/notes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteText }),
            });
            if (res.ok) {
                setNoteText('');
                setShowNoteInput(false);
                setWorkflowResult({ id: 'add_note', status: 'success', message: 'Note added to CasePeer' });
            }
        } catch (err) {
            setWorkflowResult({ id: 'add_note', status: 'error', message: err.message });
        } finally { setAddingNote(false); }
    };

    const handleCallRetry = async (callId) => {
        setCallActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/retry`, { method: 'POST' });
            setTimeout(fetchProviderCalls, 2000);
        } catch (err) { console.error('Retry failed:', err); }
        finally { setCallActionLoading(null); }
    };

    const handleCallSchedule = async (callId) => {
        const time = prompt('Schedule call for (ISO datetime):');
        if (!time) return;
        setCallActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/schedule`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scheduled_at: time }),
            });
            setTimeout(fetchProviderCalls, 1000);
        } catch (err) { console.error('Schedule failed:', err); }
        finally { setCallActionLoading(null); }
    };

    const handleCallManualEmail = async (callId) => {
        const email = prompt('Enter confirmed email address:');
        if (!email || !email.includes('@')) return;
        setCallActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/manual-email`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            setTimeout(fetchProviderCalls, 1000);
        } catch (err) { console.error('Manual email failed:', err); }
        finally { setCallActionLoading(null); }
    };

    // Helper: get calls for a specific provider name
    const getCallsForProvider = (providerName) => {
        return providerCalls.filter(c =>
            c.provider_name?.toLowerCase() === providerName?.toLowerCase()
        );
    };

    const refreshStats = async () => {
        setRefreshingStats(true);
        try {
            const res = await fetch(`/internal-api/cases/${caseId}/refresh-stats`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.case) setCaseData(prev => ({ ...prev, ...data.case }));
                setWorkflowResult({ id: 'refresh', status: 'success', message: 'Stats refreshed' });
            }
        } catch (err) {
            setWorkflowResult({ id: 'refresh', status: 'error', message: err.message });
        } finally { setRefreshingStats(false); }
    };

    const triggerWorkflow = async (wf) => {
        setRunningWorkflow(wf.id);
        setWorkflowResult(null);
        try {
            const res = await fetch(wf.endpoint(caseId), { method: 'POST' });
            if (res.ok) {
                setWorkflowResult({ id: wf.id, status: 'success', message: `${wf.name} triggered` });
            } else {
                const err = await res.text();
                setWorkflowResult({ id: wf.id, status: 'error', message: err.substring(0, 100) });
            }
        } catch (err) {
            setWorkflowResult({ id: wf.id, status: 'error', message: err.message });
        } finally {
            setRunningWorkflow(null);
        }
    };

    if (loading) return <div>Loading details...</div>;
    if (!caseData) return <div>Case not found</div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="outline" size="sm" onClick={onBack}>
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back to Cases
                    </Button>
                    <h2 className="text-3xl font-bold tracking-tight">Case: {caseData.patient_name} <span className="text-muted-foreground text-xl">#{caseData.id}</span></h2>
                </div>
                <Button
                    variant="destructive"
                    size="sm"
                    onClick={async () => {
                        if (!confirm(`Delete case ${caseData.id} and all related data?`)) return;
                        try {
                            const res = await fetch(`/internal-api/cases/${caseData.id}`, { method: 'DELETE' });
                            if (res.ok) onBack();
                        } catch (err) {
                            console.error("Failed to delete case:", err);
                        }
                    }}
                >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete Case
                </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Status</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{caseData.status || 'In Progress'}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Fees Taken</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">${caseData.fees_taken?.toFixed(2) || '0.00'}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Savings</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">${caseData.savings?.toFixed(2) || '0.00'}</div>
                    </CardContent>
                </Card>
            </div>

            {/* Workflow Action Buttons */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-lg">
                        <Zap className="h-5 w-5" />
                        Actions
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Workflows */}
                    <div>
                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Workflows</div>
                        <div className="flex flex-wrap gap-3">
                            {CASE_WORKFLOWS.map((wf) => {
                                const Icon = wf.icon;
                                const isRunning = runningWorkflow === wf.id;
                                const result = workflowResult?.id === wf.id ? workflowResult : null;
                                return (
                                    <Button
                                        key={wf.id}
                                        variant="outline"
                                        size="sm"
                                        disabled={isRunning}
                                        onClick={() => triggerWorkflow(wf)}
                                        title={wf.description}
                                        className="gap-2"
                                    >
                                        {isRunning ? (
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : result?.status === 'success' ? (
                                            <CheckCircle className="h-4 w-4 text-green-500" />
                                        ) : result?.status === 'error' ? (
                                            <XCircle className="h-4 w-4 text-red-500" />
                                        ) : (
                                            <Icon className="h-4 w-4" />
                                        )}
                                        {wf.name}
                                    </Button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Quick Actions */}
                    <div>
                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Quick Actions</div>
                        <div className="flex flex-wrap gap-3">
                            <Button variant="outline" size="sm" disabled={loadingLive === 'treatment'} onClick={() => fetchLiveData('treatment')}>
                                {loadingLive === 'treatment' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Eye className="h-4 w-4 mr-1" />}
                                View Treatment Data
                            </Button>
                            <Button variant="outline" size="sm" disabled={loadingLive === 'settlement'} onClick={() => fetchLiveData('settlement')}>
                                {loadingLive === 'settlement' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <DollarSign className="h-4 w-4 mr-1" />}
                                View Settlement Data
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => setShowNoteInput(!showNoteInput)}>
                                <StickyNote className="h-4 w-4 mr-1" />
                                Add Note
                                {showNoteInput ? <ChevronUp className="h-3 w-3 ml-1" /> : <ChevronDown className="h-3 w-3 ml-1" />}
                            </Button>
                            <Button variant="outline" size="sm" disabled={refreshingStats} onClick={refreshStats}>
                                {refreshingStats ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                                Refresh Stats
                            </Button>
                        </div>
                    </div>

                    {/* Add Note Input */}
                    {showNoteInput && (
                        <div className="flex gap-2">
                            <input
                                type="text"
                                className="flex-1 px-3 py-2 text-sm border rounded-md bg-background"
                                placeholder="Type a note to add to CasePeer..."
                                value={noteText}
                                onChange={(e) => setNoteText(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && addNote()}
                            />
                            <Button size="sm" disabled={addingNote || !noteText.trim()} onClick={addNote}>
                                {addingNote ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
                            </Button>
                        </div>
                    )}

                    {/* Result message */}
                    {workflowResult && (
                        <div className={`text-sm px-3 py-2 rounded ${workflowResult.status === 'success' ? 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300' : 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'}`}>
                            {workflowResult.message}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Live Data Viewer */}
            {liveData && (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="flex items-center justify-between text-lg">
                            <span>{liveDataType === 'treatment' ? 'Treatment Data' : 'Settlement Data'} (Live)</span>
                            <Button variant="ghost" size="sm" onClick={() => setLiveData(null)}>
                                <XCircle className="h-4 w-4" />
                            </Button>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {liveData.error ? (
                            <div className="text-red-500 text-sm">{liveData.error}</div>
                        ) : liveDataType === 'treatment' ? (
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <div className="text-sm text-muted-foreground">{liveData.patient_name}</div>
                                    <button
                                        onClick={fetchProviderCalls}
                                        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                                    >
                                        <RefreshCw className="h-3 w-3" /> Refresh calls
                                    </button>
                                </div>
                                <div className="border rounded-md overflow-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="bg-muted">
                                                <th className="p-3 text-left font-medium">Provider</th>
                                                <th className="p-3 text-left font-medium">Specialty</th>
                                                <th className="p-3 text-right font-medium">Bill</th>
                                                <th className="p-3 text-right font-medium">Offer</th>
                                                <th className="p-3 text-left font-medium">Email (CasePeer)</th>
                                                <th className="p-3 text-center font-medium">Call Status</th>
                                                <th className="p-3 text-left font-medium">Confirmed Email</th>
                                                <th className="p-3 text-center font-medium w-8"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(liveData.providers || liveData.providers_calculated || []).map((p, i) => {
                                                const calls = getCallsForProvider(p.provider_name);
                                                const latestCall = calls[0]; // most recent
                                                const isExpanded = expandedProvider === p.provider_name;
                                                return (
                                                    <React.Fragment key={i}>
                                                        <tr
                                                            className="border-t hover:bg-muted/50 cursor-pointer"
                                                            onClick={() => setExpandedProvider(isExpanded ? null : p.provider_name)}
                                                        >
                                                            <td className="p-3 font-medium">{p.provider_name}</td>
                                                            <td className="p-3 text-xs">{p.specialties}</td>
                                                            <td className="p-3 text-right">${(p.bill_amount || 0).toLocaleString()}</td>
                                                            <td className="p-3 text-right text-blue-600">${(p.offered_amount || 0).toLocaleString()}</td>
                                                            <td className="p-3 text-xs">{p.email || '-'}</td>
                                                            <td className="p-3 text-center">
                                                                {latestCall ? (
                                                                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${callStatusColors[latestCall.status] || 'bg-gray-100'}`}>
                                                                        {latestCall.status?.replace('_', ' ')}
                                                                    </span>
                                                                ) : (
                                                                    <span className="text-xs text-muted-foreground">no call</span>
                                                                )}
                                                            </td>
                                                            <td className="p-3 text-xs">
                                                                {latestCall?.confirmed_email ? (
                                                                    <span className="text-green-600 font-medium">{latestCall.confirmed_email}</span>
                                                                ) : latestCall?.email_status ? (
                                                                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${emailStatusColors[latestCall.email_status] || 'bg-gray-100'}`}>
                                                                        {latestCall.email_status?.replace('_', ' ')}
                                                                    </span>
                                                                ) : '-'}
                                                            </td>
                                                            <td className="p-3 text-center">
                                                                {calls.length > 0 && (
                                                                    isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />
                                                                )}
                                                            </td>
                                                        </tr>

                                                        {/* Expanded: show all calls for this provider */}
                                                        {isExpanded && calls.length > 0 && (
                                                            <tr>
                                                                <td colSpan={8} className="bg-muted/30 p-4 border-t">
                                                                    <div className="space-y-3">
                                                                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                                                            Call History ({calls.length} call{calls.length > 1 ? 's' : ''})
                                                                        </div>
                                                                        {calls.map((call) => (
                                                                            <div key={call.id} className="bg-background border rounded-md p-3 space-y-2">
                                                                                <div className="flex items-center justify-between">
                                                                                    <div className="flex items-center gap-2">
                                                                                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${callStatusColors[call.status] || 'bg-gray-100'}`}>
                                                                                            {call.status?.replace('_', ' ')}
                                                                                        </span>
                                                                                        <span className="text-xs text-muted-foreground">
                                                                                            Attempt {call.attempt_number || 1} &middot; {call.call_type?.replace('_', ' ')}
                                                                                        </span>
                                                                                        {call.call_duration_seconds && (
                                                                                            <span className="text-xs text-muted-foreground">&middot; {Math.round(call.call_duration_seconds)}s</span>
                                                                                        )}
                                                                                        {call.call_cost && (
                                                                                            <span className="text-xs text-muted-foreground">&middot; ${call.call_cost.toFixed(4)}</span>
                                                                                        )}
                                                                                    </div>
                                                                                    <span className="text-xs text-muted-foreground">
                                                                                        {call.created_at ? new Date(call.created_at + 'Z').toLocaleString() : ''}
                                                                                    </span>
                                                                                </div>

                                                                                {call.confirmed_email && (
                                                                                    <div className="text-sm">
                                                                                        <span className="text-muted-foreground">Confirmed: </span>
                                                                                        <span className="text-green-600 font-medium">{call.confirmed_email}</span>
                                                                                    </div>
                                                                                )}

                                                                                {call.redirect_number && (
                                                                                    <div className="text-sm">
                                                                                        <span className="text-muted-foreground">Redirect #: </span>
                                                                                        <span>{call.redirect_number}</span>
                                                                                    </div>
                                                                                )}

                                                                                {call.summary && (
                                                                                    <div className="text-xs text-muted-foreground">{call.summary}</div>
                                                                                )}

                                                                                {call.end_reason && (
                                                                                    <div className="text-xs text-muted-foreground">End: {call.end_reason}</div>
                                                                                )}

                                                                                {call.recording_url && (
                                                                                    <audio controls src={call.recording_url} className="w-full h-8" />
                                                                                )}

                                                                                {/* Actions */}
                                                                                <div className="flex gap-2 pt-1">
                                                                                    {(call.status === 'failed' || call.status === 'no_answer' || call.status === 'voicemail' || call.status === 'needs_manual') && (
                                                                                        <button
                                                                                            onClick={() => handleCallRetry(call.id)}
                                                                                            disabled={callActionLoading === call.id}
                                                                                            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
                                                                                        >
                                                                                            {callActionLoading === call.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                                                                                            Retry
                                                                                        </button>
                                                                                    )}
                                                                                    {(call.status === 'failed' || call.status === 'no_answer' || call.status === 'needs_manual') && (
                                                                                        <button
                                                                                            onClick={() => handleCallSchedule(call.id)}
                                                                                            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
                                                                                        >
                                                                                            <Calendar className="h-3 w-3" />
                                                                                            Schedule
                                                                                        </button>
                                                                                    )}
                                                                                    {call.email_status !== 'confirmed' && call.email_status !== 'new_email' && (
                                                                                        <button
                                                                                            onClick={() => handleCallManualEmail(call.id)}
                                                                                            disabled={callActionLoading === call.id}
                                                                                            className="inline-flex items-center gap-1 rounded-md bg-blue-600 text-white px-2 py-1 text-xs hover:bg-blue-700 disabled:opacity-50"
                                                                                        >
                                                                                            <Mail className="h-3 w-3" />
                                                                                            Enter Email
                                                                                        </button>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                </td>
                                                            </tr>
                                                        )}

                                                        {/* Expanded but no calls */}
                                                        {isExpanded && calls.length === 0 && (
                                                            <tr>
                                                                <td colSpan={8} className="bg-muted/30 p-4 border-t text-center text-sm text-muted-foreground">
                                                                    No calls made yet for this provider.
                                                                </td>
                                                            </tr>
                                                        )}
                                                    </React.Fragment>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Provider</TableHead>
                                            <TableHead className="text-right">Original</TableHead>
                                            <TableHead className="text-right">Final Cost</TableHead>
                                            <TableHead className="text-right">Still Owed</TableHead>
                                            <TableHead>Accepted</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {(liveData.providers || []).map((p, i) => (
                                            <TableRow key={i}>
                                                <TableCell className="font-medium">{p.provider_name}</TableCell>
                                                <TableCell className="text-right">${(p.original_cost || 0).toLocaleString()}</TableCell>
                                                <TableCell className="text-right text-blue-600">${(p.final_cost || 0).toLocaleString()}</TableCell>
                                                <TableCell className="text-right">${(p.still_owed || 0).toLocaleString()}</TableCell>
                                                <TableCell>{p.accepted ? <CheckCircle className="h-4 w-4 text-green-500" /> : '-'}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            <Tabs defaultValue="agent" className="w-full">
                <TabsList>
                    <TabsTrigger value="agent">Agent Activity</TabsTrigger>
                    <TabsTrigger value="notes">Notes</TabsTrigger>
                    <TabsTrigger value="reminders">Reminders</TabsTrigger>
                </TabsList>

                <TabsContent value="agent">
                    <AgentActivity caseId={caseId} />
                </TabsContent>

                <TabsContent value="notes">
                    <CaseNotes caseId={caseId} />
                </TabsContent>

                <TabsContent value="reminders">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Bell className="h-5 w-5" />
                                    Reminders
                                </div>
                                <span className="text-sm font-normal text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                                    {reminders.length}
                                </span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>#</TableHead>
                                        <TableHead>Date</TableHead>
                                        <TableHead>Message</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {reminders.length === 0 ? (
                                        <TableRow><TableCell colSpan={3} className="text-center">No reminders found</TableCell></TableRow>
                                    ) : (
                                        reminders.map((r) => (
                                            <TableRow key={r.id}>
                                                <TableCell>{r.reminder_number}</TableCell>
                                                <TableCell>{r.reminder_date}</TableCell>
                                                <TableCell className="max-w-md">{r.reminder_email_body}</TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
};

export default CaseDetails;
