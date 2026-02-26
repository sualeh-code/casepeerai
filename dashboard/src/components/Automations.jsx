import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Play, Square, RefreshCw, Clock, CheckCircle, XCircle, Loader2, Zap, Search, Mail, FileText, Phone, DollarSign } from 'lucide-react';
import { Input } from "@/components/ui/input";

const WORKFLOWS = [
    { id: 'initial_negotiation', name: 'Initial Negotiation', icon: Mail, description: 'Send initial offers to all providers for a case', needsCaseId: true },
    { id: 'classification', name: 'Document Classification', icon: FileText, description: 'AI classify all documents for a case', needsCaseId: true },
    { id: 'thirdparty', name: 'Third-Party Settlement', icon: DollarSign, description: 'Process defendant insurance settlement', needsCaseId: true },
    { id: 'get_mail_sub', name: 'Get Provider Emails (Vapi)', icon: Phone, description: 'Phone providers to get email addresses', needsCaseId: true },
    { id: 'case_checker', name: 'Case Checker', icon: Search, description: 'Scan CasePeer for new cases', needsCaseId: false },
    { id: 'followup', name: 'Follow-up Reminders', icon: Clock, description: 'Send reminders to unresponsive providers', needsCaseId: false },
];

const Automations = () => {
    const [schedulerStatus, setSchedulerStatus] = useState(null);
    const [runs, setRuns] = useState([]);
    const [knownCases, setKnownCases] = useState([]);
    const [loading, setLoading] = useState(true);
    const [caseInputs, setCaseInputs] = useState({});
    const [triggeringWorkflow, setTriggeringWorkflow] = useState(null);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [statusRes, runsRes, casesRes] = await Promise.all([
                fetch('/internal-api/workflows/scheduler/status'),
                fetch('/internal-api/workflows/runs?limit=30'),
                fetch('/internal-api/workflows/known-cases'),
            ]);
            if (statusRes.ok) setSchedulerStatus(await statusRes.json());
            if (runsRes.ok) {
                const data = await runsRes.json();
                setRuns(data.runs || []);
            }
            if (casesRes.ok) {
                const data = await casesRes.json();
                setKnownCases(data.cases || []);
            }
        } catch (err) {
            console.error("Error fetching automation data:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    const toggleScheduler = async () => {
        const action = schedulerStatus?.running ? 'stop' : 'start';
        try {
            const res = await fetch(`/internal-api/workflows/scheduler/${action}`, { method: 'POST' });
            if (res.ok) fetchData();
        } catch (err) {
            console.error("Scheduler toggle error:", err);
        }
    };

    const triggerWorkflow = async (wf) => {
        setTriggeringWorkflow(wf.id);
        try {
            let url;
            if (wf.needsCaseId) {
                const caseId = caseInputs[wf.id] || '';
                if (!caseId) {
                    alert('Please enter a Case ID');
                    setTriggeringWorkflow(null);
                    return;
                }
                const endpointMap = {
                    initial_negotiation: `/internal-api/workflows/initial-negotiation/${caseId}`,
                    classification: `/internal-api/workflows/classification/${caseId}`,
                    thirdparty: `/internal-api/workflows/thirdparty/${caseId}`,
                    get_mail_sub: `/internal-api/workflows/get-mail-sub/${caseId}`,
                };
                url = endpointMap[wf.id];
            } else {
                const endpointMap = {
                    case_checker: '/internal-api/workflows/case-checker/run',
                    followup: '/internal-api/workflows/followup/run',
                };
                url = endpointMap[wf.id];
            }
            const res = await fetch(url, { method: 'POST' });
            if (res.ok) {
                setTimeout(fetchData, 2000);
            }
        } catch (err) {
            console.error("Trigger error:", err);
        } finally {
            setTriggeringWorkflow(null);
        }
    };

    const statusBadge = (status) => {
        const colors = {
            running: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
            completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
            failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
        };
        const icons = {
            running: <Loader2 className="h-3 w-3 animate-spin" />,
            completed: <CheckCircle className="h-3 w-3" />,
            failed: <XCircle className="h-3 w-3" />,
        };
        return (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
                {icons[status]} {status}
            </span>
        );
    };

    if (loading) return <div className="p-4 text-muted-foreground">Loading automations...</div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-3xl font-bold tracking-tight">Automations</h2>
                <Button variant="outline" size="sm" onClick={fetchData}>
                    <RefreshCw className="h-4 w-4 mr-2" /> Refresh
                </Button>
            </div>

            {/* Scheduler Status */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <div>
                        <CardTitle className="text-lg">Daily Scheduler</CardTitle>
                        <CardDescription>Runs case checker and follow-up reminders automatically</CardDescription>
                    </div>
                    <Button
                        variant={schedulerStatus?.running ? "destructive" : "default"}
                        size="sm"
                        onClick={toggleScheduler}
                    >
                        {schedulerStatus?.running ? (
                            <><Square className="h-4 w-4 mr-2" /> Stop</>
                        ) : (
                            <><Play className="h-4 w-4 mr-2" /> Start</>
                        )}
                    </Button>
                </CardHeader>
                {schedulerStatus && (
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                            <div>
                                <span className="text-muted-foreground">Status:</span>
                                <div className="font-medium">{schedulerStatus.status}</div>
                            </div>
                            <div>
                                <span className="text-muted-foreground">Last Run:</span>
                                <div className="font-medium">{schedulerStatus.last_run || 'Never'}</div>
                            </div>
                            <div>
                                <span className="text-muted-foreground">Runs Completed:</span>
                                <div className="font-medium">{schedulerStatus.runs_completed}</div>
                            </div>
                            <div>
                                <span className="text-muted-foreground">Errors:</span>
                                <div className="font-medium">{schedulerStatus.errors}</div>
                            </div>
                        </div>
                    </CardContent>
                )}
            </Card>

            <Tabs defaultValue="trigger" className="w-full">
                <TabsList>
                    <TabsTrigger value="trigger">Trigger Workflows</TabsTrigger>
                    <TabsTrigger value="history">Run History</TabsTrigger>
                    <TabsTrigger value="cases">Known Cases</TabsTrigger>
                </TabsList>

                <TabsContent value="trigger">
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {WORKFLOWS.map((wf) => {
                            const Icon = wf.icon;
                            return (
                                <Card key={wf.id}>
                                    <CardHeader className="pb-3">
                                        <CardTitle className="text-base flex items-center gap-2">
                                            <Icon className="h-4 w-4" /> {wf.name}
                                        </CardTitle>
                                        <CardDescription className="text-xs">{wf.description}</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="flex gap-2">
                                            {wf.needsCaseId && (
                                                <Input
                                                    placeholder="Case ID"
                                                    className="w-32 h-9"
                                                    value={caseInputs[wf.id] || ''}
                                                    onChange={(e) => setCaseInputs(prev => ({ ...prev, [wf.id]: e.target.value }))}
                                                />
                                            )}
                                            <Button
                                                size="sm"
                                                onClick={() => triggerWorkflow(wf)}
                                                disabled={triggeringWorkflow === wf.id}
                                            >
                                                {triggeringWorkflow === wf.id ? (
                                                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                                                ) : (
                                                    <Zap className="h-4 w-4 mr-1" />
                                                )}
                                                Run
                                            </Button>
                                        </div>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>
                </TabsContent>

                <TabsContent value="history">
                    <Card>
                        <CardHeader>
                            <CardTitle>Workflow Run History</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Workflow</TableHead>
                                        <TableHead>Case ID</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Started</TableHead>
                                        <TableHead>Completed</TableHead>
                                        <TableHead>Triggered By</TableHead>
                                        <TableHead>Error</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {runs.length === 0 ? (
                                        <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">No workflow runs yet</TableCell></TableRow>
                                    ) : (
                                        runs.map((run) => (
                                            <TableRow key={run.id}>
                                                <TableCell className="font-medium">{run.workflow_name}</TableCell>
                                                <TableCell>{run.case_id || '-'}</TableCell>
                                                <TableCell>{statusBadge(run.status)}</TableCell>
                                                <TableCell className="text-xs text-muted-foreground">{run.started_at}</TableCell>
                                                <TableCell className="text-xs text-muted-foreground">{run.completed_at || '-'}</TableCell>
                                                <TableCell className="text-xs">{run.triggered_by}</TableCell>
                                                <TableCell className="text-xs text-red-500 max-w-[200px] truncate">{run.error || ''}</TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="cases">
                    <Card>
                        <CardHeader>
                            <CardTitle>Known Cases (Case Checker)</CardTitle>
                            <CardDescription>Cases discovered by the daily case checker</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Case ID</TableHead>
                                        <TableHead>Patient Name</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Classification</TableHead>
                                        <TableHead>Initial Negotiation</TableHead>
                                        <TableHead>Discovered</TableHead>
                                        <TableHead>Last Checked</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {knownCases.length === 0 ? (
                                        <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">No cases tracked yet. Run the Case Checker to start.</TableCell></TableRow>
                                    ) : (
                                        knownCases.map((c) => (
                                            <TableRow key={c.case_id}>
                                                <TableCell className="font-medium">{c.case_id}</TableCell>
                                                <TableCell>{c.patient_name || '-'}</TableCell>
                                                <TableCell>{c.status || '-'}</TableCell>
                                                <TableCell>{statusBadge(c.classification_status || 'pending')}</TableCell>
                                                <TableCell>{statusBadge(c.initial_negotiation_status || 'pending')}</TableCell>
                                                <TableCell className="text-xs text-muted-foreground">{c.discovered_at}</TableCell>
                                                <TableCell className="text-xs text-muted-foreground">{c.last_checked || '-'}</TableCell>
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

export default Automations;
