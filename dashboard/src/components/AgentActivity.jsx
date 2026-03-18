import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bot, ChevronLeft, ChevronRight, Wrench, CheckCircle, Clock, AlertTriangle, Send, Inbox, ChevronDown, ChevronUp, Mail, DollarSign, Search, Loader2, XCircle } from 'lucide-react';

const StatusBadge = ({ intent }) => {
    const lower = (intent || '').toLowerCase();
    if (lower.includes('accepted')) return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle className="h-3 w-3" /> Accepted
        </span>
    );
    if (lower.includes('escalate')) return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <AlertTriangle className="h-3 w-3" /> Escalated
        </span>
    );
    if (lower.includes('rejected')) return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
            Rejected
        </span>
    );
    if (lower.includes('bill_confirmation')) return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            Bill Confirmed
        </span>
    );
    return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
            <Clock className="h-3 w-3" /> {intent || 'In Progress'}
        </span>
    );
};

const TimelineItem = ({ item }) => {
    const [expanded, setExpanded] = useState(false);
    const isOutbound = item.direction === 'outbound';
    const content = item.email_body || '';
    const isLong = content.length > 300;

    return (
        <div className={`relative pl-6 pb-4 border-l-2 ${isOutbound ? 'border-blue-300' : 'border-green-300'}`}>
            <div className={`absolute -left-[7px] top-0 w-3 h-3 rounded-full ${isOutbound ? 'bg-blue-500' : 'bg-green-500'}`} />
            <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-muted-foreground font-mono">{item.timestamp}</span>
                    <span className={`inline-flex items-center gap-1 text-xs font-medium ${isOutbound ? 'text-blue-600' : 'text-green-600'}`}>
                        {isOutbound ? <Send className="h-3 w-3" /> : <Inbox className="h-3 w-3" />}
                        {isOutbound ? 'Us' : 'Provider'}
                    </span>
                    <StatusBadge intent={item.negotiation_type || item.result} />
                </div>
                {(item.actual_bill > 0 || item.offered_bill > 0) && (
                    <div className="flex gap-3 text-xs">
                        {item.actual_bill > 0 && <span className="text-muted-foreground">Bill: <strong>${item.actual_bill.toLocaleString()}</strong></span>}
                        {item.offered_bill > 0 && <span className="text-muted-foreground">Offer: <strong className="text-blue-600">${item.offered_bill.toLocaleString()}</strong></span>}
                    </div>
                )}
                {content && (
                    <div className="mt-1 text-sm bg-muted/50 rounded p-2">
                        <div
                            className="whitespace-pre-wrap break-words"
                            dangerouslySetInnerHTML={{
                                __html: expanded || !isLong ? content : content.substring(0, 300) + '...'
                            }}
                        />
                        {isLong && (
                            <button
                                onClick={() => setExpanded(!expanded)}
                                className="text-xs text-blue-600 hover:underline mt-1 flex items-center gap-1"
                            >
                                {expanded ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> Show more</>}
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

const ConversationCard = ({ conv }) => {
    const [expanded, setExpanded] = useState(false);

    return (
        <Card className="mb-3">
            <CardHeader className="py-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                        <StatusBadge intent={conv.last_intent} />
                        <span className="text-muted-foreground">{conv.updated_at}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {conv.tools_used && conv.tools_used.length > 0 && (
                            <div className="flex gap-1">
                                {conv.tools_used.map((tool, ti) => (
                                    <span key={ti} className="inline-flex items-center gap-1 bg-muted text-xs px-1.5 py-0.5 rounded">
                                        <Wrench className="h-3 w-3" /> {tool}
                                    </span>
                                ))}
                            </div>
                        )}
                        {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </div>
                </div>
            </CardHeader>
            {expanded && (
                <CardContent className="py-2 space-y-2">
                    {(conv.chat || []).map((msg, mi) => {
                        if (msg.role === 'system') return null;
                        const isAssistant = msg.role === 'assistant';
                        const isTool = msg.role === 'tool';

                        return (
                            <div key={mi} className={`text-sm p-3 rounded ${
                                isAssistant ? 'bg-blue-50 dark:bg-blue-950 border-l-2 border-blue-400' :
                                isTool ? 'bg-amber-50 dark:bg-amber-950 border-l-2 border-amber-400 font-mono text-xs' :
                                'bg-gray-50 dark:bg-gray-900 border-l-2 border-gray-400'
                            }`}>
                                <div className="text-xs font-bold mb-1 text-muted-foreground">
                                    {isAssistant ? 'AI Agent' : isTool ? 'Tool Result' : 'Context'}
                                    {msg.function && <span className="ml-1 text-amber-600">({msg.function})</span>}
                                </div>
                                <div className="whitespace-pre-wrap break-words">
                                    {msg.content || (msg.arguments ? `Call: ${msg.function}(${msg.arguments})` : '(no content)')}
                                </div>
                            </div>
                        );
                    })}
                </CardContent>
            )}
        </Card>
    );
};

const AgentActivity = ({ caseId }) => {
    const [providers, setProviders] = useState([]);
    const [selectedProvider, setSelectedProvider] = useState(null);
    const [selectedProviderName, setSelectedProviderName] = useState('');
    const [providerHistory, setProviderHistory] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadingHistory, setLoadingHistory] = useState(false);
    const [actionLoading, setActionLoading] = useState(null);
    const [actionResult, setActionResult] = useState(null);
    const [lookupResults, setLookupResults] = useState(null);

    useEffect(() => {
        const fetchProviders = async () => {
            setLoading(true);
            try {
                const res = await fetch(`/internal-api/cases/${caseId}/agent/providers`);
                if (res.ok) {
                    const data = await res.json();
                    setProviders(data.providers || []);
                }
            } catch (err) {
                console.error("Error fetching agent providers:", err);
            } finally {
                setLoading(false);
            }
        };
        if (caseId) fetchProviders();
    }, [caseId]);

    const fetchProviderHistory = async (email, providerName) => {
        setLoadingHistory(true);
        setSelectedProvider(email);
        setSelectedProviderName(providerName || '');
        try {
            const res = await fetch(`/internal-api/cases/${caseId}/agent/providers/${encodeURIComponent(email)}/history`);
            if (res.ok) {
                setProviderHistory(await res.json());
            }
        } catch (err) {
            console.error("Error fetching provider history:", err);
        } finally {
            setLoadingHistory(false);
        }
    };

    const resendLetter = async (providerEmail, providerName) => {
        setActionLoading('resend');
        setActionResult(null);
        try {
            const res = await fetch(`/internal-api/cases/${caseId}/providers/${encodeURIComponent(providerEmail)}/resend-letter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_name: providerName }),
            });
            const data = await res.json();
            if (res.ok) setActionResult({ status: 'success', message: data.message || 'Letter sent' });
            else setActionResult({ status: 'error', message: data.detail || 'Failed' });
        } catch (err) { setActionResult({ status: 'error', message: err.message }); }
        finally { setActionLoading(null); }
    };

    const lookupContact = async (providerName) => {
        setActionLoading('lookup');
        setActionResult(null);
        setLookupResults(null);
        try {
            const res = await fetch(`/internal-api/providers/lookup/${encodeURIComponent(providerName)}`);
            if (res.ok) {
                const data = await res.json();
                setLookupResults(data.contacts || []);
            } else { setActionResult({ status: 'error', message: 'Lookup failed' }); }
        } catch (err) { setActionResult({ status: 'error', message: err.message }); }
        finally { setActionLoading(null); }
    };

    // Derive provider name: API data > timeline > email fallback
    const getProviderName = () => {
        if (selectedProviderName) return selectedProviderName;
        if (providerHistory) {
            for (const item of (providerHistory.timeline || [])) {
                if (item.provider_name) return item.provider_name;
            }
        }
        return selectedProvider;
    };

    if (loading) return <div className="p-4 text-muted-foreground">Loading agent activity...</div>;

    // Provider detail view
    if (selectedProvider && providerHistory) {
        const providerName = getProviderName();
        return (
            <div className="space-y-4">
                <Button variant="outline" size="sm" onClick={() => { setSelectedProvider(null); setSelectedProviderName(''); setProviderHistory(null); setActionResult(null); setLookupResults(null); }}>
                    <ChevronLeft className="h-4 w-4 mr-1" /> Back to providers
                </Button>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Bot className="h-5 w-5" />
                            {providerName !== selectedProvider ? `${providerName} — ` : ''}{selectedProvider}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        {/* Provider Actions */}
                        <div>
                            <h3 className="font-semibold mb-3 text-sm uppercase tracking-wide text-muted-foreground">Actions</h3>
                            <div className="flex flex-wrap gap-2">
                                <Button variant="outline" size="sm" disabled={actionLoading === 'resend'} onClick={() => resendLetter(selectedProvider, providerName)}>
                                    {actionLoading === 'resend' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Mail className="h-4 w-4 mr-1" />}
                                    Resend Offer Letter
                                </Button>
                                <Button variant="outline" size="sm" disabled={actionLoading === 'lookup'} onClick={() => lookupContact(providerName)}>
                                    {actionLoading === 'lookup' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Search className="h-4 w-4 mr-1" />}
                                    Lookup Contact Info
                                </Button>
                            </div>
                            {actionResult && (
                                <div className={`mt-2 text-sm px-3 py-2 rounded ${actionResult.status === 'success' ? 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300' : 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'}`}>
                                    {actionResult.message}
                                </div>
                            )}
                            {lookupResults && (
                                <div className="mt-2 border rounded p-3 space-y-2">
                                    <div className="text-xs font-semibold text-muted-foreground">Contact Directory Results ({lookupResults.length})</div>
                                    {lookupResults.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">No contacts found</div>
                                    ) : lookupResults.map((c, i) => (
                                        <div key={i} className="text-sm border-b last:border-0 pb-2 last:pb-0">
                                            <div className="font-medium">{c.name || c[0] || 'Unknown'}</div>
                                            {c.email && <div className="text-xs text-muted-foreground">Email: {c.email}</div>}
                                            {c.phone && <div className="text-xs text-muted-foreground">Phone: {c.phone}</div>}
                                            {c.full_text && <div className="text-xs text-muted-foreground">{c.full_text}</div>}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Timeline */}
                        {providerHistory.timeline && providerHistory.timeline.length > 0 && (
                            <div>
                                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wide text-muted-foreground">Negotiation Timeline</h3>
                                <div className="ml-1">
                                    {providerHistory.timeline.map((item, i) => (
                                        <TimelineItem key={i} item={item} />
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* AI Conversations */}
                        {providerHistory.conversations && providerHistory.conversations.length > 0 && (
                            <div>
                                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wide text-muted-foreground">AI Conversations</h3>
                                {providerHistory.conversations.map((conv, ci) => (
                                    <ConversationCard key={ci} conv={conv} />
                                ))}
                            </div>
                        )}

                        {(!providerHistory.timeline || providerHistory.timeline.length === 0) &&
                         (!providerHistory.conversations || providerHistory.conversations.length === 0) && (
                            <div className="text-center text-muted-foreground py-8">No agent activity found.</div>
                        )}
                    </CardContent>
                </Card>
            </div>
        );
    }

    // Provider list view
    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Bot className="h-5 w-5" />
                        Providers
                    </div>
                    <span className="text-sm font-normal text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                        {providers.length}
                    </span>
                </CardTitle>
            </CardHeader>
            <CardContent>
                {providers.length === 0 ? (
                    <div className="text-center text-muted-foreground py-8">
                        No AI agent interactions recorded yet.
                    </div>
                ) : (
                    <div className="space-y-2">
                        {providers.map((p, i) => {
                            const intent = (p.last_intent || '').toLowerCase();
                            return (
                                <div
                                    key={i}
                                    className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 cursor-pointer transition-colors"
                                    onClick={() => fetchProviderHistory(p.email, p.provider_name)}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`w-2 h-2 rounded-full ${
                                            intent.includes('accepted') ? 'bg-green-500' :
                                            intent.includes('escalate') ? 'bg-red-500' :
                                            'bg-blue-500'
                                        }`} />
                                        <div>
                                            {p.provider_name && <div className="font-medium text-sm">{p.provider_name}</div>}
                                            <div className={`text-sm ${p.provider_name ? 'text-muted-foreground text-xs' : 'font-medium'}`}>{p.email}</div>
                                            <div className="text-xs text-muted-foreground">
                                                {p.negotiation_count} interactions &middot; {p.last_activity || 'No activity'}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="text-right text-xs">
                                            {p.latest_bill > 0 && <div className="text-muted-foreground">Bill: ${p.latest_bill.toLocaleString()}</div>}
                                            {p.latest_offer > 0 && <div className="font-medium text-blue-600">Offer: ${p.latest_offer.toLocaleString()}</div>}
                                        </div>
                                        <StatusBadge intent={p.last_intent} />
                                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </CardContent>
        </Card>
    );
};

export default AgentActivity;
