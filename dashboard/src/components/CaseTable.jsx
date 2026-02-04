import React, { useEffect, useState } from 'react';
import {
    Table,
    TableBody,
    TableCaption,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import FileUpload from './FileUpload';

const CaseTable = ({ onCaseSelect }) => {
    const [cases, setCases] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchCases = async () => {
        try {
            const response = await fetch('/api/cases');
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

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold tracking-tight">Case Management</h2>
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
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {cases.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center h-24 text-muted-foreground">
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
