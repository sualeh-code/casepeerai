
import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, FileText, Bell, MessageSquare, Eye, RefreshCw, Globe, StickyNote } from 'lucide-react';
import CaseNotes from './CaseNotes';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"

const CaseDetails = ({ caseId, onBack }) => {
    const [caseData, setCaseData] = useState(null);
    const [negotiations, setNegotiations] = useState([]);
    const [liveNegotiations, setLiveNegotiations] = useState([]);
    const [classifications, setClassifications] = useState([]);
    const [reminders, setReminders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingLive, setLoadingLive] = useState(false);
    const [selectedEmail, setSelectedEmail] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                // Fetch basic case info
                const caseRes = await fetch(`/internal-api/cases/${caseId}`);
                if (caseRes.ok) setCaseData(await caseRes.json());

                // Fetch related data
                const [negRes, classRes, remRes] = await Promise.all([
                    fetch(`/internal-api/negotiations?case_id=${caseId}`),
                    fetch(`/internal-api/classifications?case_id=${caseId}`),
                    fetch(`/internal-api/reminders?case_id=${caseId}`)
                ]);

                if (negRes.ok) setNegotiations(await negRes.json());
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

    const fetchLiveData = async () => {
        setLoadingLive(true);
        try {
            const response = await fetch(`/internal-api/live/cases/${caseId}/negotiations`);
            if (response.ok) {
                const data = await response.json();
                setLiveNegotiations(data.negotiations || []);
            }
        } catch (error) {
            console.error("Error fetching live data:", error);
        } finally {
            setLoadingLive(false);
        }
    };

    if (loading) return <div>Loading details...</div>;
    if (!caseData) return <div>Case not found</div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-4">
                <Button variant="outline" size="sm" onClick={onBack}>
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back to Cases
                </Button>
                <h2 className="text-3xl font-bold tracking-tight">Case: {caseData.patient_name} <span className="text-muted-foreground text-xl">#{caseData.id}</span></h2>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Status</CardTitle>
                        <FileText className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{caseData.status}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Fees Taken</CardTitle>
                        <span className="text-muted-foreground">$</span>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">${caseData.fees_taken?.toFixed(2)}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Savings</CardTitle>
                        <span className="text-muted-foreground">$</span>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">${caseData.savings?.toFixed(2)}</div>
                    </CardContent>
                </Card>
            </div>

            <Tabs defaultValue="negotiations" className="w-full">
                <TabsList>
                    <TabsTrigger value="negotiations">Negotiations</TabsTrigger>
                    <TabsTrigger value="notes">Notes</TabsTrigger>
                    <TabsTrigger value="classifications">Classifications</TabsTrigger>
                    <TabsTrigger value="reminders">Reminders</TabsTrigger>
                </TabsList>

                <TabsContent value="negotiations">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <MessageSquare className="h-5 w-5" />
                                    Stored Negotiations
                                </div>
                                <span className="text-sm font-normal text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                                    {negotiations.length}
                                </span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Type</TableHead>
                                        <TableHead>To</TableHead>
                                        <TableHead>Date</TableHead>
                                        <TableHead>Preview</TableHead>
                                        <TableHead>Actual Bill</TableHead>
                                        <TableHead>Offered</TableHead>
                                        <TableHead>Result</TableHead>
                                        <TableHead>Email</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {negotiations.length === 0 ? (
                                        <TableRow><TableCell colSpan={8} className="text-center">No negotiations recorded</TableCell></TableRow>
                                    ) : (
                                        negotiations.map((n) => (
                                            <TableRow key={n.id}>
                                                <TableCell>{n.negotiation_type}</TableCell>
                                                <TableCell>{n.to}</TableCell>
                                                <TableCell>{n.date}</TableCell>
                                                <TableCell>
                                                    <div className="max-w-[200px] truncate text-xs text-muted-foreground">
                                                        {n.email_body || "No body"}
                                                    </div>
                                                </TableCell>
                                                <TableCell>${n.actual_bill?.toFixed(2)}</TableCell>
                                                <TableCell>${n.offered_bill?.toFixed(2)}</TableCell>
                                                <TableCell>{n.result}</TableCell>
                                                <TableCell>
                                                    <Dialog>
                                                        <DialogTrigger asChild>
                                                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                                                                <Eye className="h-4 w-4" />
                                                            </Button>
                                                        </DialogTrigger>
                                                        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                                                            <DialogHeader>
                                                                <DialogTitle>Negotiation Email Body</DialogTitle>
                                                            </DialogHeader>
                                                            <div className="mt-4 p-4 bg-muted rounded-md whitespace-pre-wrap font-mono text-sm">
                                                                {n.email_body || "No email body recorded."}
                                                            </div>
                                                        </DialogContent>
                                                    </Dialog>
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>


                <TabsContent value="notes">
                    <CaseNotes caseId={caseId} />
                </TabsContent>

                <TabsContent value="classifications">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2"><FileText className="h-5 w-5" /> Classifications (OCR)</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>OCR Performed</TableHead>
                                        <TableHead>Doc Count</TableHead>
                                        <TableHead>Confidence</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {classifications.length === 0 ? (
                                        <TableRow><TableCell colSpan={3} className="text-center">No classifications found</TableCell></TableRow>
                                    ) : (
                                        classifications.map((c) => (
                                            <TableRow key={c.id}>
                                                <TableCell>{c.ocr_performed ? "Yes" : "No"}</TableCell>
                                                <TableCell>{c.number_of_documents}</TableCell>
                                                <TableCell>{(c.confidence * 100).toFixed(1)}%</TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
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
                                        <TableHead>Message (Click eye to view)</TableHead>
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
                                                <TableCell className="flex items-center gap-2">
                                                    <span className="max-w-md truncate" title={r.reminder_email_body}>
                                                        {r.reminder_email_body}
                                                    </span>
                                                    <Dialog>
                                                        <DialogTrigger asChild>
                                                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                                                                <Eye className="h-4 w-4" />
                                                            </Button>
                                                        </DialogTrigger>
                                                        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                                                            <DialogHeader>
                                                                <DialogTitle>Reminder Email Body</DialogTitle>
                                                            </DialogHeader>
                                                            <div className="mt-4 p-4 bg-muted rounded-md whitespace-pre-wrap font-mono text-sm">
                                                                {r.reminder_email_body || "No email body recorded."}
                                                            </div>
                                                        </DialogContent>
                                                    </Dialog>
                                                </TableCell>
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
