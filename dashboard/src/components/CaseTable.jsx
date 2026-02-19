import React, { useEffect, useState } from 'react';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Trash2 } from 'lucide-react';

const CaseTable = ({ onCaseSelect }) => {
    const [cases, setCases] = useState([]);
    const [loading, setLoading] = useState(true);
    const [deleting, setDeleting] = useState(null);

    const fetchCases = async () => {
        try {
            const response = await fetch('/internal-api/cases');
            if (response.ok) {
                const data = await response.json();
                setCases(data);
            }
        } catch (error) {
            console.error("Failed to fetch cases:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCases();
    }, []);

    const handleDeleteCase = async (e, caseId) => {
        e.stopPropagation();
        if (!confirm(`Delete case ${caseId} and all its related data?`)) return;
        setDeleting(caseId);
        try {
            const res = await fetch(`/internal-api/cases/${caseId}`, { method: 'DELETE' });
            if (res.ok) {
                setCases(prev => prev.filter(c => c.id !== caseId));
            }
        } catch (err) {
            console.error("Failed to delete case:", err);
        } finally {
            setDeleting(null);
        }
    };

    const handleDeleteAll = async () => {
        if (!confirm(`Delete ALL ${cases.length} cases and all related data? This cannot be undone.`)) return;
        try {
            const res = await fetch('/internal-api/cases', { method: 'DELETE' });
            if (res.ok) {
                setCases([]);
            }
        } catch (err) {
            console.error("Failed to delete all cases:", err);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold tracking-tight">Case Management</h2>
                {cases.length > 0 && (
                    <Button variant="destructive" size="sm" onClick={handleDeleteAll}>
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete All Cases
                    </Button>
                )}
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Cases</CardTitle>
                    <CardDescription>A list of all cases. Click on a row to view details.</CardDescription>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Case ID</TableHead>
                                <TableHead>Patient Name</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Fees Taken</TableHead>
                                <TableHead>Savings</TableHead>
                                <TableHead className="w-[60px]"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {cases.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={6} className="text-center h-24 text-muted-foreground">
                                        No cases found. Use the API to add cases.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                cases.map((c) => (
                                    <TableRow
                                        key={c.id}
                                        className="cursor-pointer hover:bg-muted/80"
                                        onClick={() => onCaseSelect && onCaseSelect(c.id)}
                                    >
                                        <TableCell className="font-medium">{c.id}</TableCell>
                                        <TableCell>{c.patient_name}</TableCell>
                                        <TableCell>{c.status}</TableCell>
                                        <TableCell>${c.fees_taken?.toFixed(2)}</TableCell>
                                        <TableCell>${c.savings?.toFixed(2)}</TableCell>
                                        <TableCell>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                                                onClick={(e) => handleDeleteCase(e, c.id)}
                                                disabled={deleting === c.id}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </TableCell>
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

export default CaseTable;
