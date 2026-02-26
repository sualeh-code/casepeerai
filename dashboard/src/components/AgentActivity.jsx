import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Bot, Wrench, ChevronRight, ChevronLeft, MessageSquare, Eye } from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";

const AgentActivity = ({ caseId }) => {
    const [providers, setProviders] = useState([]);
    const [selectedProvider, setSelectedProvider] = useState(null);
    const [providerHistory, setProviderHistory] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadingHistory, setLoadingHistory] = useState(false);

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

    const fetchProviderHistory = async (email) => {
        setLoadingHistory(true);
        setSelectedProvider(email);
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

    if (loading) return <div className="p-4 text-muted-foreground">Loading agent activity...</div>;

    // Provider detail view
    if (selectedProvider && providerHistory) {
        return (
            <div className="space-y-4">
                <Button variant="outline" size="sm" onClick={() => { setSelectedProvider(null); setProviderHistory(null); }}>
                    <ChevronLeft className="h-4 w-4 mr-1" /> Back to providers
                </Button>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Bot className="h-5 w-5" />
                            Agent History: {selectedProvider}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        {/* Timeline */}
                        {providerHistory.timeline && providerHistory.timeline.length > 0 && (
                            <div>
                                <h3 className="font-semibold mb-3">Negotiation Timeline</h3>
                                <div className="space-y-2">
                                    {providerHistory.timeline.map((item, i) => (
                                        <div key={i} className="flex items-start gap-3 p-2 rounded border text-sm">
                                            <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${item.direction === 'outbound' ? 'bg-blue-500' : 'bg-green-500'}`} />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <span>{item.timestamp}</span>
                                                    <span className="font-medium">{item.direction === 'outbound' ? 'Us' : 'Provider'}</span>
                                                    <span className="bg-muted px-1.5 py-0.5 rounded">{item.negotiation_type}</span>
                                                    {item.result && <span className="text-green-600">{item.result}</span>}
                                                </div>
                                                <div className="mt-1 truncate">{item.email_body}</div>
                                                {(item.actual_bill || item.offered_bill) && (
                                                    <div className="text-xs text-muted-foreground mt-0.5">
                                                        {item.actual_bill ? `Bill: $${item.actual_bill}` : ''}
                                                        {item.actual_bill && item.offered_bill ? ' | ' : ''}
                                                        {item.offered_bill ? `Offer: $${item.offered_bill}` : ''}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Conversations with tool history */}
                        {providerHistory.conversations && providerHistory.conversations.length > 0 && (
                            <div>
                                <h3 className="font-semibold mb-3">AI Conversations</h3>
                                {providerHistory.conversations.map((conv, ci) => (
                                    <Card key={ci} className="mb-4">
                                        <CardHeader className="py-3">
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="font-medium">{conv.thread_subject}</span>
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <span>Intent: <strong>{conv.last_intent}</strong></span>
                                                    <span>{conv.updated_at}</span>
                                                </div>
                                            </div>
                                            {conv.tools_used && conv.tools_used.length > 0 && (
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {conv.tools_used.map((tool, ti) => (
                                                        <span key={ti} className="inline-flex items-center gap-1 bg-muted text-xs px-2 py-0.5 rounded">
                                                            <Wrench className="h-3 w-3" /> {tool}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </CardHeader>
                                        <CardContent className="py-2">
                                            <div className="space-y-2 max-h-[400px] overflow-y-auto">
                                                {(conv.chat || []).map((msg, mi) => {
                                                    if (msg.role === 'system') return null;
                                                    const isAssistant = msg.role === 'assistant';
                                                    const isTool = msg.role === 'tool';
                                                    const isUser = msg.role === 'user';

                                                    return (
                                                        <div key={mi} className={`text-sm p-2 rounded ${
                                                            isAssistant ? 'bg-blue-50 dark:bg-blue-950 border-l-2 border-blue-400' :
                                                            isTool ? 'bg-amber-50 dark:bg-amber-950 border-l-2 border-amber-400 font-mono text-xs' :
                                                            isUser ? 'bg-gray-50 dark:bg-gray-900 border-l-2 border-gray-400' : ''
                                                        }`}>
                                                            <div className="text-xs font-bold mb-1 text-muted-foreground">
                                                                {isAssistant ? 'AI Agent' : isTool ? 'Tool Result' : 'Context'}
                                                                {msg.function && <span className="ml-1 text-amber-600">({msg.function})</span>}
                                                            </div>
                                                            <div className="whitespace-pre-wrap break-words">
                                                                {msg.content
                                                                    ? (msg.content.length > 500
                                                                        ? msg.content.substring(0, 500) + '...'
                                                                        : msg.content)
                                                                    : msg.arguments
                                                                        ? `Call: ${msg.function}(${msg.arguments.substring(0, 200)}${msg.arguments.length > 200 ? '...' : ''})`
                                                                        : '(no content)'}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}

                        {(!providerHistory.timeline || providerHistory.timeline.length === 0) &&
                         (!providerHistory.conversations || providerHistory.conversations.length === 0) && (
                            <div className="text-center text-muted-foreground py-8">No agent activity found for this provider.</div>
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
                        Agent Activity by Provider
                    </div>
                    <span className="text-sm font-normal text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                        {providers.length} provider{providers.length !== 1 ? 's' : ''}
                    </span>
                </CardTitle>
            </CardHeader>
            <CardContent>
                {providers.length === 0 ? (
                    <div className="text-center text-muted-foreground py-8">
                        No AI agent interactions recorded for this case yet.
                    </div>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Provider Email</TableHead>
                                <TableHead>Negotiations</TableHead>
                                <TableHead>Last Activity</TableHead>
                                <TableHead>Latest Bill</TableHead>
                                <TableHead>Latest Offer</TableHead>
                                <TableHead>Last Intent</TableHead>
                                <TableHead></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {providers.map((p, i) => (
                                <TableRow key={i} className="cursor-pointer hover:bg-muted/50" onClick={() => fetchProviderHistory(p.email)}>
                                    <TableCell className="font-medium">{p.email}</TableCell>
                                    <TableCell>{p.negotiation_count}</TableCell>
                                    <TableCell className="text-sm text-muted-foreground">{p.last_activity || '-'}</TableCell>
                                    <TableCell>{p.latest_bill ? `$${p.latest_bill}` : '-'}</TableCell>
                                    <TableCell>{p.latest_offer ? `$${p.latest_offer}` : '-'}</TableCell>
                                    <TableCell>
                                        {p.last_intent && (
                                            <span className="bg-muted text-xs px-2 py-0.5 rounded">{p.last_intent}</span>
                                        )}
                                    </TableCell>
                                    <TableCell>
                                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
            </CardContent>
        </Card>
    );
};

export default AgentActivity;
