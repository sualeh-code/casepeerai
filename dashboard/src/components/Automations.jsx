import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Play, Square, RefreshCw, Clock, CheckCircle, XCircle, Loader2, Zap, Search } from 'lucide-react';

const GLOBAL_WORKFLOWS = [
    { id: 'case_checker', name: 'Case Checker', icon: Search, description: 'Scan CasePeer for new cases', endpoint: '/internal-api/workflows/case-checker/run' },
    { id: 'followup', name: 'Follow-up Reminders', icon: Clock, description: 'Send reminders to unresponsive providers', endpoint: '/internal-api/workflows/followup/run' },
];

const Automations = () => {
    const [schedulerStatus, setSchedulerStatus] = useState(null);
    const [runs, setRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [triggeringWorkflow, setTriggeringWorkflow] = useState(null);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [statusRes, runsRes] = await Promise.all([
                fetch('/internal-api/workflows/scheduler/status'),
                fetch('/internal-api/workflows/runs?limit=30'),
            ]);
            if (statusRes.ok) setSchedulerStatus(await statusRes.json());
            if (runsRes.ok) {
                const data = await runsRes.json();
                setRuns(data.runs || []);
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
            const res = await fetch(wf.endpoint, { method: 'POST' });
            if (res.ok) setTimeout(fetchData, 2000);
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

            {/* Scheduler + Global Workflows */}
            <div className="grid gap-4 md:grid-cols-2">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <div>
                            <CardTitle className="text-lg">Daily Scheduler</CardTitle>
                            <CardDescription>Runs case checker and follow-ups automatically</CardDescription>
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
                            <div className="grid grid-cols-2 gap-4 text-sm">
                                <div>
                                    <span className="text-muted-foreground">Status:</span>
                                    <div className="font-medium">{schedulerStatus.status}</div>
                                </div>
                                <div>
                                    <span className="text-muted-foreground">Last Run:</span>
                                    <div className="font-medium">{schedulerStatus.last_run || 'Never'}</div>
                                </div>
                                <div>
                                    <span className="text-muted-foreground">Runs:</span>
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

                {GLOBAL_WORKFLOWS.map((wf) => {
                    const Icon = wf.icon;
                    return (
                        <Card key={wf.id}>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <div>
                                    <CardTitle className="text-lg flex items-center gap-2">
                                        <Icon className="h-5 w-5" /> {wf.name}
                                    </CardTitle>
                                    <CardDescription>{wf.description}</CardDescription>
                                </div>
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
                                    Run Now
                                </Button>
                            </CardHeader>
                        </Card>
                    );
                })}
            </div>

            <Card className="text-sm text-muted-foreground px-4 py-3">
                Case-specific workflows (Initial Negotiation, Classification, Third-Party Settlement, Get Provider Emails) are available inside each case's detail page.
            </Card>

            {/* Run History */}
            <Card>
                <CardHeader>
                    <CardTitle>Run History</CardTitle>
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
        </div>
    );
};

export default Automations;
