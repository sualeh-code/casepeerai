import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bot, ChevronLeft, ChevronRight, Wrench, CheckCircle, Clock, AlertTriangle, Send, Inbox, ChevronDown, ChevronUp, Mail, DollarSign, Search, Loader2, XCircle, FileCheck, MessageSquare, ArrowRightLeft, HandCoins, CircleDot, HelpCircle, BanIcon } from 'lucide-react';

// ─── Intent configuration ──────────────────────────────────────────
// Maps every possible AI agent intent to a human-readable label, color, icon, and sort priority
const INTENT_CONFIG = {
    // Active negotiations (priority 1 - needs attention)
    rejected:                  { label: 'Counter-Offered',    color: 'bg-orange-100 text-orange-800', icon: ArrowRightLeft, priority: 1, tip: 'Provider countered or rejected — negotiation ongoing' },
    asked_for_clarification:   { label: 'Question Asked',     color: 'bg-purple-100 text-purple-800', icon: HelpCircle,     priority: 1, tip: 'Provider asked a question — reply sent' },
    asking_for_payment:        { label: 'Awaiting Payment',   color: 'bg-yellow-100 text-yellow-800', icon: HandCoins,      priority: 1, tip: 'Provider asking when they\'ll be paid' },
    bill_correction:           { label: 'Bill Corrected',     color: 'bg-amber-100 text-amber-800',   icon: FileCheck,      priority: 1, tip: 'Provider stated a different bill amount — recalculating' },

    // Waiting for response (priority 2)
    initial_outreach:          { label: 'Offer Sent',         color: 'bg-blue-100 text-blue-800',     icon: Send,           priority: 2, tip: 'Initial offer letter sent — waiting for response' },
    bill_confirmation:         { label: 'Bill Confirmed',     color: 'bg-sky-100 text-sky-800',       icon: CheckCircle,    priority: 2, tip: 'Provider confirmed the bill amount — offer made' },
    resend_offer_letter:       { label: 'Letter Re-sent',     color: 'bg-blue-100 text-blue-800',     icon: Mail,           priority: 2, tip: 'Offer letter was re-sent to the provider' },

    // Resolved (priority 3)
    accepted:                  { label: 'Accepted',           color: 'bg-green-100 text-green-800',   icon: CheckCircle,    priority: 3, tip: 'Provider accepted our offer — letter sent for signing' },
    accepted_and_provided_details: { label: 'Finalized',      color: 'bg-emerald-100 text-emerald-800', icon: CheckCircle,  priority: 3, tip: 'Provider signed letter + provided payment details — done' },
    provided_details:          { label: 'Details Received',   color: 'bg-teal-100 text-teal-800',     icon: FileCheck,      priority: 3, tip: 'Provider sent W9 or payment info' },

    // Needs human attention (priority 4)
    escalate:                  { label: 'Escalated',          color: 'bg-red-100 text-red-800',       icon: AlertTriangle,  priority: 4, tip: 'Needs human review — provider threatened legal action or all tactics exhausted' },

    // Inactive (priority 5)
    no_action:                 { label: 'No Reply Needed',    color: 'bg-gray-100 text-gray-600',     icon: BanIcon,        priority: 5, tip: 'Auto-reply, out-of-office, or no action required' },
    unclear:                   { label: 'Under Review',       color: 'bg-gray-100 text-gray-600',     icon: Clock,          priority: 5, tip: 'Intent unclear — may need manual review' },
};

const getIntentConfig = (intent) => {
    const key = (intent || '').toLowerCase().trim();
    // Exact match first
    if (INTENT_CONFIG[key]) return INTENT_CONFIG[key];
    // Partial match fallback for compound intents
    for (const [k, v] of Object.entries(INTENT_CONFIG)) {
        if (key.includes(k)) return v;
    }
    return { label: intent || 'In Progress', color: 'bg-gray-100 text-gray-700', icon: Clock, priority: 5, tip: '' };
};

const StatusBadge = ({ intent }) => {
    const config = getIntentConfig(intent);
    const Icon = config.icon;
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.color}`}
            title={config.tip}>
            <Icon className="h-3 w-3" /> {config.label}
        </span>
    );
};

// ─── Sort providers by intent priority then activity ───────────────
const sortProviders = (providers) => {
    return [...providers].sort((a, b) => {
        const pa = getIntentConfig(a.last_intent).priority;
        const pb = getIntentConfig(b.last_intent).priority;
        if (pa !== pb) return pa - pb;
        // Same priority: sort by most recent activity
        return (b.last_activity || '').localeCompare(a.last_activity || '');
    });
};

// ─── Status dot color ──────────────────────────────────────────────
const getStatusDotColor = (intent) => {
    const p = getIntentConfig(intent).priority;
    if (p === 1) return 'bg-orange-500';  // Active — needs attention
    if (p === 2) return 'bg-blue-500';    // Waiting for response
    if (p === 3) return 'bg-green-500';   // Resolved
    if (p === 4) return 'bg-red-500';     // Escalated
    return 'bg-gray-400';                 // Inactive
};

// ─── Sub-components ────────────────────────────────────────────────
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
                    {item.email && <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{item.email}</span>}
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
                        {conv.email && <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{conv.email}</span>}
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

// ─── Section grouping labels ───────────────────────────────────────
const SECTION_LABELS = {
    1: { label: 'Needs Attention', desc: 'Active negotiations requiring a response' },
    2: { label: 'Waiting for Response', desc: 'Offers sent, awaiting provider reply' },
    3: { label: 'Resolved', desc: 'Provider accepted or provided payment details' },
    4: { label: 'Escalated', desc: 'Needs human review' },
    5: { label: 'Inactive', desc: 'No action needed or unclear' },
};

// ─── Main Component ────────────────────────────────────────────────
const AgentActivity = ({ caseId }) => {
    const [providers, setProviders] = useState([]);
    const [selectedProvider, setSelectedProvider] = useState(null);
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

    const fetchProviderHistory = async (provider) => {
        setLoadingHistory(true);
        setSelectedProvider(provider);
        setActionResult(null);
        setLookupResults(null);
        try {
            const emails = provider.emails.map(e => e.email);
            const primaryEmail = emails[0];
            const emailsParam = emails.length > 1 ? `?emails=${encodeURIComponent(emails.join(','))}` : '';
            const res = await fetch(`/internal-api/cases/${caseId}/agent/providers/${encodeURIComponent(primaryEmail)}/history${emailsParam}`);
            if (res.ok) {
                setProviderHistory(await res.json());
            }
        } catch (err) {
            console.error("Error fetching provider history:", err);
        } finally {
            setLoadingHistory(false);
        }
    };

    const resendLetter = async (providerEmail) => {
        setActionLoading('resend');
        setActionResult(null);
        try {
            const res = await fetch(`/internal-api/cases/${caseId}/providers/${encodeURIComponent(providerEmail)}/resend-letter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_name: selectedProvider?.provider_name || '' }),
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

    if (loading) return <div className="p-4 text-muted-foreground">Loading agent activity...</div>;

    // ═════════════════════════════════════════════════════
    // Provider detail view (emails + timeline + conversations)
    // ═════════════════════════════════════════════════════
    if (selectedProvider && providerHistory) {
        const providerName = selectedProvider.provider_name || selectedProvider.emails[0]?.email || 'Unknown';
        const allEmails = selectedProvider.emails || [];

        return (
            <div className="space-y-4">
                <Button variant="outline" size="sm" onClick={() => { setSelectedProvider(null); setProviderHistory(null); setActionResult(null); setLookupResults(null); }}>
                    <ChevronLeft className="h-4 w-4 mr-1" /> Back to providers
                </Button>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Bot className="h-5 w-5" />
                            {providerName}
                        </CardTitle>
                        <CardDescription>
                            Full negotiation history with this provider across {allEmails.length} email address{allEmails.length !== 1 ? 'es' : ''}.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        {/* Email addresses for this provider */}
                        <div>
                            <h3 className="font-semibold mb-2 text-sm uppercase tracking-wide text-muted-foreground">
                                Email Addresses ({allEmails.length})
                            </h3>
                            <div className="space-y-1">
                                {allEmails.map((em, i) => (
                                    <div key={i} className="flex items-center justify-between p-2 rounded border bg-muted/30 text-sm">
                                        <div className="flex items-center gap-2">
                                            <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                                            <span className="font-mono text-xs">{em.email}</span>
                                            {em.last_intent && <StatusBadge intent={em.last_intent} />}
                                        </div>
                                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                            {em.negotiation_count > 0 && <span>{em.negotiation_count} email{em.negotiation_count !== 1 ? 's' : ''}</span>}
                                            {em.latest_offer > 0 && <span className="text-blue-600 font-medium">Offer: ${em.latest_offer.toLocaleString()}</span>}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Provider Actions */}
                        <div>
                            <h3 className="font-semibold mb-3 text-sm uppercase tracking-wide text-muted-foreground">Actions</h3>
                            <div className="flex flex-wrap gap-2">
                                {allEmails.map((em, i) => (
                                    <Button key={i} variant="outline" size="sm" disabled={actionLoading === 'resend'}
                                        onClick={() => resendLetter(em.email)}>
                                        {actionLoading === 'resend' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Mail className="h-4 w-4 mr-1" />}
                                        Resend Letter → {em.email.split('@')[0]}
                                    </Button>
                                ))}
                                {selectedProvider.provider_name && (
                                    <Button variant="outline" size="sm" disabled={actionLoading === 'lookup'} onClick={() => lookupContact(selectedProvider.provider_name)}>
                                        {actionLoading === 'lookup' ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Search className="h-4 w-4 mr-1" />}
                                        Lookup Contact Info
                                    </Button>
                                )}
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

                        {/* Combined Timeline */}
                        {providerHistory.timeline && providerHistory.timeline.length > 0 && (
                            <div>
                                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wide text-muted-foreground">
                                    Negotiation Timeline ({providerHistory.timeline.length} events)
                                </h3>
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
                                <h3 className="font-semibold mb-3 text-sm uppercase tracking-wide text-muted-foreground">
                                    AI Conversations ({providerHistory.conversations.length})
                                </h3>
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

    // Loading state for provider detail
    if (selectedProvider && loadingHistory) {
        return (
            <div className="space-y-4">
                <Button variant="outline" size="sm" onClick={() => setSelectedProvider(null)}>
                    <ChevronLeft className="h-4 w-4 mr-1" /> Back to providers
                </Button>
                <div className="p-8 text-center text-muted-foreground animate-pulse">Loading provider history...</div>
            </div>
        );
    }

    // ═════════════════════════════════════════════════════
    // Provider list — sorted by priority, grouped by section
    // ═════════════════════════════════════════════════════
    const sorted = sortProviders(providers);

    // Group into sections by priority
    const sections = [];
    let currentPriority = null;
    for (const p of sorted) {
        const priority = getIntentConfig(p.last_intent).priority;
        if (priority !== currentPriority) {
            currentPriority = priority;
            sections.push({ priority, label: SECTION_LABELS[priority]?.label || 'Other', desc: SECTION_LABELS[priority]?.desc || '', providers: [] });
        }
        sections[sections.length - 1].providers.push(p);
    }

    return (
        <div className="space-y-1">
            {providers.length === 0 ? (
                <div className="text-center text-muted-foreground py-8">
                    No AI agent interactions recorded yet.
                </div>
            ) : (
                sections.map((section, si) => (
                    <div key={si}>
                        <div className="px-4 pt-4 pb-2">
                            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{section.label}</div>
                            <div className="text-xs text-muted-foreground">{section.desc}</div>
                        </div>
                        <div className="space-y-1 px-2 pb-2">
                            {section.providers.map((p, i) => {
                                const emailCount = (p.emails || []).length;
                                const displayName = p.provider_name || (p.emails?.[0]?.email || 'Unknown');

                                return (
                                    <div
                                        key={i}
                                        className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 cursor-pointer transition-colors"
                                        onClick={() => fetchProviderHistory(p)}
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${getStatusDotColor(p.last_intent)}`} />
                                            <div className="min-w-0">
                                                <div className="font-medium text-sm">{displayName}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {emailCount} email{emailCount !== 1 ? 's' : ''}
                                                    {p.total_negotiations > 0 && <> &middot; {p.total_negotiations} round{p.total_negotiations !== 1 ? 's' : ''}</>}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-3 flex-shrink-0">
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
                    </div>
                ))
            )}
        </div>
    );
};

export default AgentActivity;
