
import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, FileText, Bell, Bot, Trash2, Mail, DollarSign, Loader2, CheckCircle, XCircle, Zap, RefreshCw, StickyNote, ChevronDown, ChevronUp, PhoneCall, Calendar, AlertTriangle, HelpCircle } from 'lucide-react';
import CaseNotes from './CaseNotes';
import AgentActivity from './AgentActivity';

// ─── Status badge helpers ────────────────────────────────────────────
const callStatusConfig = {
    queued:       { color: 'bg-gray-100 text-gray-800',   label: 'Queued',       tip: 'Waiting to be dialed' },
    scheduled:    { color: 'bg-purple-100 text-purple-800', label: 'Scheduled',   tip: 'Will call at the scheduled time' },
    ringing:      { color: 'bg-yellow-100 text-yellow-800', label: 'Ringing',     tip: 'Phone is ringing now' },
    in_progress:  { color: 'bg-blue-100 text-blue-800',   label: 'In Progress',  tip: 'Currently on the call' },
    ended:        { color: 'bg-green-100 text-green-800',  label: 'Ended',        tip: 'Call completed' },
    failed:       { color: 'bg-red-100 text-red-800',     label: 'Failed',       tip: 'Call failed — will retry' },
    no_answer:    { color: 'bg-orange-100 text-orange-800', label: 'No Answer',   tip: 'No one picked up — will retry' },
    voicemail:    { color: 'bg-amber-100 text-amber-800',  label: 'Voicemail',    tip: 'Reached voicemail — will retry' },
    needs_manual: { color: 'bg-red-200 text-red-900',     label: 'Needs Manual', tip: 'Max retries reached — enter email manually' },
};

const emailStatusConfig = {
    pending:      { color: 'bg-yellow-100 text-yellow-800', label: 'Pending',      tip: 'Waiting for call result' },
    confirmed:    { color: 'bg-green-100 text-green-800',  label: 'Confirmed',    tip: 'Provider confirmed the email on file' },
    new_email:    { color: 'bg-blue-100 text-blue-800',   label: 'New Email',    tip: 'Provider gave a different email' },
    not_obtained: { color: 'bg-red-100 text-red-800',     label: 'Not Obtained', tip: 'Could not get email from this call' },
};

const StatusBadge = ({ value, config }) => {
    const entry = config[value] || { color: 'bg-gray-100 text-gray-700', label: value || '-', tip: '' };
    return (
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${entry.color}`}
            title={entry.tip}>
            {entry.label}
        </span>
    );
};

// ─── Workflows ───────────────────────────────────────────────────────
const CASE_WORKFLOWS = [
    { id: 'initial_negotiation', name: 'Send Initial Offers', icon: Mail,
        description: 'Email every provider with a negotiation offer based on their bill amount',
        endpoint: (caseId) => `/internal-api/workflows/initial-negotiation/${caseId}` },
    { id: 'classification', name: 'Classify Documents', icon: FileText,
        description: 'Use AI to categorize all uploaded case documents (medical records, bills, etc.)',
        endpoint: (caseId) => `/internal-api/workflows/classification/${caseId}` },
    { id: 'thirdparty', name: 'Third-Party Settlement', icon: DollarSign,
        description: 'Process the defendant insurance company settlement calculation',
        endpoint: (caseId) => `/internal-api/workflows/thirdparty/${caseId}` },
    { id: 'provider_calls', name: 'Call All Providers', icon: PhoneCall,
        description: 'AI phone call to every provider to confirm or get their email address',
        endpoint: (caseId) => `/internal-api/provider-calls/${caseId}/trigger` },
];

// ─── Main Component ──────────────────────────────────────────────────
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

    // ─── Data fetching ───────────────────────────────────────────────
    const fetchProviderCalls = async () => {
        try {
            const res = await fetch(`/internal-api/provider-calls/${caseId}`);
            if (res.ok) { const data = await res.json(); setProviderCalls(data.calls || []); }
        } catch (err) { console.error("Error fetching provider calls:", err); }
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
                try {
                    const treatRes = await fetch(`/internal-api/cases/${caseId}/live/treatment`);
                    if (treatRes.ok) { setLiveData(await treatRes.json()); setLiveDataType('treatment'); }
                } catch (e) { /* non-critical */ }
                await fetchProviderCalls();
            } catch (error) { console.error("Error fetching case details:", error); }
            finally { setLoading(false); }
        };
        if (caseId) fetchData();
    }, [caseId]);

    // ─── Actions ─────────────────────────────────────────────────────
    const fetchLiveData = async (type) => {
        setLoadingLive(type); setLiveDataType(type);
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
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteText }),
            });
            if (res.ok) {
                setNoteText(''); setShowNoteInput(false);
                setWorkflowResult({ id: 'add_note', status: 'success', message: 'Note added to CasePeer' });
            }
        } catch (err) { setWorkflowResult({ id: 'add_note', status: 'error', message: err.message }); }
        finally { setAddingNote(false); }
    };

    const handleCallSingleProvider = async (providerName, providerPhone, existingEmail) => {
        setCallActionLoading(providerName);
        try {
            const res = await fetch(`/internal-api/provider-calls/${caseId}/trigger-single`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_name: providerName, provider_phone: providerPhone, existing_email: existingEmail || '' }),
            });
            if (res.ok) {
                setWorkflowResult({ id: 'single_call', status: 'success', message: `Call triggered for ${providerName}` });
                setTimeout(fetchProviderCalls, 3000);
            }
        } catch (err) { console.error('Single call failed:', err); }
        finally { setCallActionLoading(null); }
    };

    const handleCallRetry = async (callId) => {
        setCallActionLoading(callId);
        try { await fetch(`/internal-api/provider-calls/${callId}/retry`, { method: 'POST' }); setTimeout(fetchProviderCalls, 2000); }
        catch (err) { console.error('Retry failed:', err); }
        finally { setCallActionLoading(null); }
    };

    const handleCallSchedule = async (callId) => {
        const time = prompt('Schedule call for (e.g. "2025-04-03T10:00" or "tomorrow 10am"):');
        if (!time) return;
        setCallActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/schedule`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scheduled_at: time }),
            });
            setTimeout(fetchProviderCalls, 1000);
        } catch (err) { console.error('Schedule failed:', err); }
        finally { setCallActionLoading(null); }
    };

    const handleCallManualEmail = async (callId) => {
        const email = prompt('Enter the confirmed email address:');
        if (!email || !email.includes('@')) return;
        setCallActionLoading(callId);
        try {
            await fetch(`/internal-api/provider-calls/${callId}/manual-email`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            setTimeout(fetchProviderCalls, 1000);
        } catch (err) { console.error('Manual email failed:', err); }
        finally { setCallActionLoading(null); }
    };

    const getCallsForProvider = (providerName) =>
        providerCalls.filter(c => c.provider_name?.toLowerCase() === providerName?.toLowerCase());

    const refreshStats = async () => {
        setRefreshingStats(true);
        try {
            const res = await fetch(`/internal-api/cases/${caseId}/refresh-stats`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.case) setCaseData(prev => ({ ...prev, ...data.case }));
                setWorkflowResult({ id: 'refresh', status: 'success', message: 'Stats refreshed from CasePeer' });
            }
        } catch (err) { setWorkflowResult({ id: 'refresh', status: 'error', message: err.message }); }
        finally { setRefreshingStats(false); }
    };

    const triggerWorkflow = async (wf) => {
        setRunningWorkflow(wf.id); setWorkflowResult(null);
        try {
            const res = await fetch(wf.endpoint(caseId), { method: 'POST' });
            if (res.ok) setWorkflowResult({ id: wf.id, status: 'success', message: `${wf.name} started successfully` });
            else { const err = await res.text(); setWorkflowResult({ id: wf.id, status: 'error', message: err.substring(0, 100) }); }
        } catch (err) { setWorkflowResult({ id: wf.id, status: 'error', message: err.message }); }
        finally { setRunningWorkflow(null); }
    };

    // ─── Loading / Error ─────────────────────────────────────────────
    if (loading) return <div className="p-8 text-muted-foreground">Loading case details...</div>;
    if (!caseData) return <div className="p-8 text-muted-foreground">Case not found</div>;

    // ─── Render ──────────────────────────────────────────────────────
    return (
        <div className="space-y-6">
            {/* ── Header ── */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="outline" size="sm" onClick={onBack}>
                        <ArrowLeft className="h-4 w-4 mr-2" /> Back
                    </Button>
                    <div>
                        <h2 className="text-2xl font-bold tracking-tight">{caseData.patient_name}</h2>
                        <p className="text-sm text-muted-foreground">Case #{caseData.id}</p>
                    </div>
                </div>
                <Button variant="destructive" size="sm"
                    onClick={async () => {
                        if (!confirm(`Delete case ${caseData.id} and all related data? This cannot be undone.`)) return;
                        try { const res = await fetch(`/internal-api/cases/${caseData.id}`, { method: 'DELETE' }); if (res.ok) onBack(); }
                        catch (err) { console.error("Failed to delete case:", err); }
                    }}>
                    <Trash2 className="h-4 w-4 mr-2" /> Delete Case
                </Button>
            </div>

            {/* ── Summary Cards ── */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Case Status</CardTitle></CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{caseData.status || 'In Progress'}</div>
                        <p className="text-xs text-muted-foreground mt-1">Current stage in CasePeer</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Attorney Fees</CardTitle></CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">${caseData.fees_taken?.toFixed(2) || '0.00'}</div>
                        <p className="text-xs text-muted-foreground mt-1">Firm's fee from this case</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Client Savings</CardTitle></CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">${caseData.savings?.toFixed(2) || '0.00'}</div>
                        <p className="text-xs text-muted-foreground mt-1">Reduced from original provider bills via negotiation</p>
                    </CardContent>
                </Card>
            </div>

            {/* ── Workflows & Quick Actions ── */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-lg"><Zap className="h-5 w-5" /> Actions</CardTitle>
                    <CardDescription>Run AI workflows on this case or fetch live data from CasePeer.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Workflows */}
                    <div>
                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">AI Workflows</div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {CASE_WORKFLOWS.map((wf) => {
                                const Icon = wf.icon;
                                const isRunning = runningWorkflow === wf.id;
                                const result = workflowResult?.id === wf.id ? workflowResult : null;
                                return (
                                    <button key={wf.id} disabled={isRunning}
                                        onClick={() => triggerWorkflow(wf)}
                                        className="flex items-start gap-3 p-3 rounded-lg border text-left hover:bg-muted/50 transition-colors disabled:opacity-50">
                                        <div className="mt-0.5">
                                            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> :
                                                result?.status === 'success' ? <CheckCircle className="h-4 w-4 text-green-500" /> :
                                                result?.status === 'error' ? <XCircle className="h-4 w-4 text-red-500" /> :
                                                <Icon className="h-4 w-4 text-muted-foreground" />}
                                        </div>
                                        <div>
                                            <div className="text-sm font-medium">{wf.name}</div>
                                            <div className="text-xs text-muted-foreground">{wf.description}</div>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Quick Actions */}
                    <div>
                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Quick Actions</div>
                        <div className="flex flex-wrap gap-2">
                            <Button variant="outline" size="sm" disabled={loadingLive === 'treatment'} onClick={() => fetchLiveData('treatment')}>
                                {loadingLive === 'treatment' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <PhoneCall className="h-4 w-4 mr-1" />}
                                Treatment Providers
                            </Button>
                            <Button variant="outline" size="sm" disabled={loadingLive === 'settlement'} onClick={() => fetchLiveData('settlement')}>
                                {loadingLive === 'settlement' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <DollarSign className="h-4 w-4 mr-1" />}
                                Settlement Status
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => setShowNoteInput(!showNoteInput)}>
                                <StickyNote className="h-4 w-4 mr-1" /> Add Note
                                {showNoteInput ? <ChevronUp className="h-3 w-3 ml-1" /> : <ChevronDown className="h-3 w-3 ml-1" />}
                            </Button>
                            <Button variant="outline" size="sm" disabled={refreshingStats} onClick={refreshStats}>
                                {refreshingStats ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                                Refresh Stats
                            </Button>
                        </div>
                    </div>

                    {/* Note Input */}
                    {showNoteInput && (
                        <div className="flex gap-2">
                            <input type="text" className="flex-1 px-3 py-2 text-sm border rounded-md bg-background"
                                placeholder="Type a note to add to this case in CasePeer..."
                                value={noteText} onChange={(e) => setNoteText(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && addNote()} />
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

            {/* ── Live Data: Treatment Providers ── */}
            {liveData && liveDataType === 'treatment' && !liveData.error && (
                <Card>
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-lg">Treatment Providers</CardTitle>
                                <CardDescription>
                                    Medical providers who treated {liveData.patient_name || 'the patient'}.
                                    Each row shows their bill, our negotiation offer, and email contact status.
                                    Click a row to see call history.
                                </CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <button onClick={fetchProviderCalls}
                                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                                    <RefreshCw className="h-3 w-3" /> Refresh
                                </button>
                                <Button variant="ghost" size="sm" onClick={() => { setLiveData(null); setLiveDataType(null); }}>
                                    <XCircle className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="border rounded-md overflow-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="bg-muted">
                                        <th className="p-3 text-left font-medium">Provider</th>
                                        <th className="p-3 text-right font-medium" title="Original bill amount from the provider">Bill</th>
                                        <th className="p-3 text-right font-medium" title="Our negotiation offer sent to the provider">Our Offer</th>
                                        <th className="p-3 text-left font-medium" title="Email address on file in CasePeer">Email</th>
                                        <th className="p-3 text-center font-medium" title="Status of the AI phone call to this provider">Phone Call</th>
                                        <th className="p-3 text-center font-medium" title="Click the Call button to have AI call this provider">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {[...(liveData.providers || liveData.providers_calculated || [])]
                                    .sort((a, b) => (b.bill_amount || 0) - (a.bill_amount || 0))
                                    .map((p, i) => {
                                        const calls = getCallsForProvider(p.provider_name);
                                        const latestCall = calls[0];
                                        const isExpanded = expandedProvider === p.provider_name;
                                        const confirmedEmail = latestCall?.confirmed_email;
                                        const isZeroBill = !(p.bill_amount > 0);
                                        return (
                                            <React.Fragment key={i}>
                                                <tr className={`border-t hover:bg-muted/50 cursor-pointer ${isZeroBill ? 'opacity-50' : ''}`}
                                                    onClick={() => setExpandedProvider(isExpanded ? null : p.provider_name)}>
                                                    <td className="p-3">
                                                        <div className="font-medium">{p.provider_name}</div>
                                                        {p.specialties && <div className="text-xs text-muted-foreground">{p.specialties}</div>}
                                                    </td>
                                                    <td className="p-3 text-right font-mono">${(p.bill_amount || 0).toLocaleString()}</td>
                                                    <td className="p-3 text-right font-mono text-blue-600">${(p.offered_amount || 0).toLocaleString()}</td>
                                                    <td className="p-3">
                                                        <div className="text-xs">{p.email || <span className="text-muted-foreground">no email</span>}</div>
                                                        {confirmedEmail && confirmedEmail !== p.email && (
                                                            <div className="text-xs text-green-600 font-medium mt-0.5" title="Email confirmed or obtained via phone call">
                                                                {confirmedEmail}
                                                            </div>
                                                        )}
                                                    </td>
                                                    <td className="p-3 text-center">
                                                        {latestCall ? (
                                                            <div className="space-y-1">
                                                                <StatusBadge value={latestCall.status} config={callStatusConfig} />
                                                                {latestCall.email_status && latestCall.email_status !== 'pending' && (
                                                                    <div><StatusBadge value={latestCall.email_status} config={emailStatusConfig} /></div>
                                                                )}
                                                            </div>
                                                        ) : (
                                                            <span className="text-xs text-muted-foreground">not called</span>
                                                        )}
                                                    </td>
                                                    <td className="p-3 text-center">
                                                        <div className="flex items-center gap-1 justify-center">
                                                            {p.phone && (
                                                                <button
                                                                    onClick={(e) => { e.stopPropagation(); handleCallSingleProvider(p.provider_name, p.phone, p.email); }}
                                                                    disabled={callActionLoading === p.provider_name}
                                                                    className="inline-flex items-center gap-1 rounded-md bg-green-600 text-white px-2 py-0.5 text-xs font-medium hover:bg-green-700 disabled:opacity-50"
                                                                    title={`AI will call ${p.phone} to confirm email`}>
                                                                    {callActionLoading === p.provider_name ? <Loader2 className="h-3 w-3 animate-spin" /> : <PhoneCall className="h-3 w-3" />}
                                                                    Call
                                                                </button>
                                                            )}
                                                            {!p.phone && <span className="text-xs text-muted-foreground">no phone</span>}
                                                            {calls.length > 0 && (isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />)}
                                                        </div>
                                                    </td>
                                                </tr>

                                                {/* ── Expanded: Call History ── */}
                                                {isExpanded && (
                                                    <tr>
                                                        <td colSpan={6} className="bg-muted/30 p-4 border-t">
                                                            {calls.length === 0 ? (
                                                                <div className="text-center text-sm text-muted-foreground py-2">
                                                                    No calls made yet. Click the green "Call" button to start.
                                                                </div>
                                                            ) : (
                                                                <div className="space-y-3">
                                                                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                                                        Call History ({calls.length} call{calls.length > 1 ? 's' : ''})
                                                                    </div>
                                                                    {calls.map((call) => (
                                                                        <div key={call.id} className="bg-background border rounded-md p-3 space-y-2">
                                                                            <div className="flex items-center justify-between">
                                                                                <div className="flex items-center gap-2 flex-wrap">
                                                                                    <StatusBadge value={call.status} config={callStatusConfig} />
                                                                                    <StatusBadge value={call.email_status} config={emailStatusConfig} />
                                                                                    <span className="text-xs text-muted-foreground">
                                                                                        Attempt {call.attempt_number || 1}
                                                                                        {call.call_duration_seconds ? ` \u00b7 ${Math.round(call.call_duration_seconds)}s` : ''}
                                                                                        {call.call_cost ? ` \u00b7 $${call.call_cost.toFixed(4)}` : ''}
                                                                                    </span>
                                                                                </div>
                                                                                <span className="text-xs text-muted-foreground">
                                                                                    {call.created_at ? new Date(call.created_at + 'Z').toLocaleString() : ''}
                                                                                </span>
                                                                            </div>

                                                                            {call.confirmed_email && (
                                                                                <div className="text-sm">
                                                                                    <span className="text-muted-foreground">Email obtained: </span>
                                                                                    <span className="text-green-600 font-medium">{call.confirmed_email}</span>
                                                                                </div>
                                                                            )}

                                                                            {call.summary && (
                                                                                <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                                                                    <span className="font-medium">AI Summary: </span>{call.summary}
                                                                                </div>
                                                                            )}

                                                                            {call.end_reason && (
                                                                                <div className="text-xs text-muted-foreground">
                                                                                    End reason: {call.end_reason.replace(/[-_]/g, ' ')}
                                                                                </div>
                                                                            )}

                                                                            {call.recording_url && (
                                                                                <audio controls src={call.recording_url} className="w-full h-8" />
                                                                            )}

                                                                            {/* Call Actions */}
                                                                            <div className="flex gap-2 pt-1">
                                                                                {(call.status === 'failed' || call.status === 'no_answer' || call.status === 'voicemail' || call.status === 'needs_manual') && (
                                                                                    <button onClick={() => handleCallRetry(call.id)}
                                                                                        disabled={callActionLoading === call.id}
                                                                                        className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
                                                                                        title="Try calling this provider again">
                                                                                        {callActionLoading === call.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                                                                                        Retry
                                                                                    </button>
                                                                                )}
                                                                                {(call.status === 'failed' || call.status === 'no_answer' || call.status === 'needs_manual') && (
                                                                                    <button onClick={() => handleCallSchedule(call.id)}
                                                                                        className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
                                                                                        title="Schedule this call for a specific time">
                                                                                        <Calendar className="h-3 w-3" /> Schedule
                                                                                    </button>
                                                                                )}
                                                                                {call.email_status !== 'confirmed' && call.email_status !== 'new_email' && (
                                                                                    <button onClick={() => handleCallManualEmail(call.id)}
                                                                                        disabled={callActionLoading === call.id}
                                                                                        className="inline-flex items-center gap-1 rounded-md bg-blue-600 text-white px-2 py-1 text-xs hover:bg-blue-700 disabled:opacity-50"
                                                                                        title="Manually enter the email if you got it another way">
                                                                                        <Mail className="h-3 w-3" /> Enter Email
                                                                                    </button>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </td>
                                                    </tr>
                                                )}
                                            </React.Fragment>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* ── Live Data: Settlement ── */}
            {liveData && liveDataType === 'settlement' && !liveData.error && (
                <Card>
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-lg">Settlement Status</CardTitle>
                                <CardDescription>
                                    Current negotiation results for each provider.
                                    "Original" is the full bill. "Final Cost" is what we negotiated it down to.
                                    "Still Owed" is the remaining balance after payments.
                                </CardDescription>
                            </div>
                            <Button variant="ghost" size="sm" onClick={() => { setLiveData(null); setLiveDataType(null); }}>
                                <XCircle className="h-4 w-4" />
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Provider</TableHead>
                                    <TableHead className="text-right" title="Original bill amount before negotiation">Original Bill</TableHead>
                                    <TableHead className="text-right" title="Amount we negotiated the bill down to">Negotiated To</TableHead>
                                    <TableHead className="text-right" title="Remaining balance after any payments">Still Owed</TableHead>
                                    <TableHead title="Whether the provider accepted our offer">Accepted</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {(liveData.providers || []).map((p, i) => (
                                    <TableRow key={i}>
                                        <TableCell className="font-medium">{p.provider_name}</TableCell>
                                        <TableCell className="text-right font-mono">${(p.original_cost || 0).toLocaleString()}</TableCell>
                                        <TableCell className="text-right font-mono text-blue-600">${(p.final_cost || 0).toLocaleString()}</TableCell>
                                        <TableCell className="text-right font-mono">${(p.still_owed || 0).toLocaleString()}</TableCell>
                                        <TableCell>{p.accepted ? <CheckCircle className="h-4 w-4 text-green-500" /> : <span className="text-muted-foreground">-</span>}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}

            {/* ── Live Data: Error ── */}
            {liveData?.error && (
                <Card>
                    <CardContent className="p-4">
                        <div className="text-red-600 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4" /> {liveData.error}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* ── Tabs: Agent Activity / Notes / Reminders ── */}
            <Tabs defaultValue="agent" className="w-full">
                <TabsList>
                    <TabsTrigger value="agent">Negotiation History</TabsTrigger>
                    <TabsTrigger value="notes">Case Notes</TabsTrigger>
                    <TabsTrigger value="reminders">Follow-up Reminders</TabsTrigger>
                </TabsList>

                <TabsContent value="agent">
                    <Card>
                        <CardHeader className="pb-2">
                            <CardDescription>
                                Email negotiations between the AI agent and each provider.
                                Click a provider to see the full email thread, AI decisions, and negotiation timeline.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="p-0">
                            <AgentActivity caseId={caseId} />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="notes">
                    <CaseNotes caseId={caseId} />
                </TabsContent>

                <TabsContent value="reminders">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Bell className="h-5 w-5" /> Follow-up Reminders
                            </CardTitle>
                            <CardDescription>
                                Automated follow-up emails sent to providers who haven't responded to our offers.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-16">#</TableHead>
                                        <TableHead>Date Sent</TableHead>
                                        <TableHead>Message</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {reminders.length === 0 ? (
                                        <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground">No follow-up reminders sent yet</TableCell></TableRow>
                                    ) : reminders.map((r) => (
                                        <TableRow key={r.id}>
                                            <TableCell>{r.reminder_number}</TableCell>
                                            <TableCell>{r.reminder_date}</TableCell>
                                            <TableCell className="max-w-md text-sm">{r.reminder_email_body}</TableCell>
                                        </TableRow>
                                    ))}
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
