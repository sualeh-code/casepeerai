
import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, FileText, Bell, Bot, Trash2, Mail, DollarSign, Phone, Loader2, CheckCircle, XCircle, Zap } from 'lucide-react';
import CaseNotes from './CaseNotes';
import AgentActivity from './AgentActivity';

const CASE_WORKFLOWS = [
    { id: 'initial_negotiation', name: 'Send Initial Offers', icon: Mail, description: 'Email all providers with initial negotiation offers', endpoint: (caseId) => `/internal-api/workflows/initial-negotiation/${caseId}` },
    { id: 'classification', name: 'Classify Documents', icon: FileText, description: 'AI classify all case documents', endpoint: (caseId) => `/internal-api/workflows/classification/${caseId}` },
    { id: 'thirdparty', name: 'Third-Party Settlement', icon: DollarSign, description: 'Process defendant insurance settlement', endpoint: (caseId) => `/internal-api/workflows/thirdparty/${caseId}` },
    { id: 'get_mail_sub', name: 'Get Provider Emails', icon: Phone, description: 'Phone providers to get email addresses', endpoint: (caseId) => `/internal-api/workflows/get-mail-sub/${caseId}` },
];

const CaseDetails = ({ caseId, onBack }) => {
    const [caseData, setCaseData] = useState(null);
    const [classifications, setClassifications] = useState([]);
    const [reminders, setReminders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [runningWorkflow, setRunningWorkflow] = useState(null);
    const [workflowResult, setWorkflowResult] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const caseRes = await fetch(`/internal-api/cases/${caseId}`);
                if (caseRes.ok) setCaseData(await caseRes.json());

                const [classRes, remRes] = await Promise.all([
                    fetch(`/internal-api/classifications?case_id=${caseId}`),
                    fetch(`/internal-api/reminders?case_id=${caseId}`)
                ]);

                if (classRes.ok) setClassifications(await classRes.json());
                if (remRes.ok) setReminders(await remRes.json());
            } catch (error) {
                console.error("Error fetching case details:", error);
            } finally {
                setLoading(false);
            }
        };

        if (caseId) fetchData();
    }, [caseId]);

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
                <CardContent>
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
                    {workflowResult && (
                        <div className={`mt-3 text-sm px-3 py-2 rounded ${workflowResult.status === 'success' ? 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300' : 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'}`}>
                            {workflowResult.message}
                        </div>
                    )}
                </CardContent>
            </Card>

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
