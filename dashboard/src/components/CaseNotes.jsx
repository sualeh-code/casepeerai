
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { StickyNote, RefreshCw, AlertCircle } from 'lucide-react';

const CaseNotes = ({ caseId }) => {
    const [notes, setNotes] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchNotes = async () => {
        if (!caseId) return;
        setLoading(true);
        setError(null);
        try {
            // Proxy request to CasePeer via our backend
            // URL: /case/{caseId}/notes/api/case-notes-table/
            const response = await fetch(`/case/${caseId}/notes/api/case-notes-table/`);

            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error("Notes endpoint not found (404). Check proxy configuration.");
                } else if (response.status === 401 || response.status === 403) {
                    throw new Error("Authentication failed. Please check backend logs.");
                } else {
                    throw new Error(`Failed to fetch notes: ${response.statusText}`);
                }
            }

            const data = await response.json();
            // CasePeer API usually returns { results: [...] } or just [...]
            // Let's handle both
            const results = Array.isArray(data) ? data : (data.results || []);
            setNotes(results);

        } catch (err) {
            console.error("Error fetching notes:", err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchNotes();
    }, [caseId]);

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <StickyNote className="h-5 w-5" />
                        Case Notes
                    </div>
                    <Button variant="outline" size="sm" onClick={fetchNotes} disabled={loading}>
                        {loading ? <RefreshCw className="h-3 w-3 animate-spin mr-2" /> : <RefreshCw className="h-3 w-3 mr-2" />}
                        Refresh Notes
                    </Button>
                </CardTitle>
                <CardDescription>
                    Live notes fetched directly from CasePeer.
                </CardDescription>
            </CardHeader>
            <CardContent>
                {error && (
                    <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-md flex items-center gap-2 text-sm">
                        <AlertCircle className="h-4 w-4" />
                        {error}
                    </div>
                )}

                <div className="rounded-md border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Date</TableHead>
                                <TableHead>Author</TableHead>
                                <TableHead>Note</TableHead>
                                <TableHead>Type</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {notes.length === 0 && !loading && !error ? (
                                <TableRow>
                                    <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                                        No notes found for this case.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                notes.map((note, idx) => (
                                    <TableRow key={note.id || idx}>
                                        <TableCell className="whitespace-nowrap font-medium text-xs">
                                            {note.created_at || note.date || "Unknown Date"}
                                        </TableCell>
                                        <TableCell className="text-xs">
                                            {note.created_by || note.author || "Unknown"}
                                        </TableCell>
                                        <TableCell className="max-w-xl">
                                            <div className="whitespace-pre-wrap text-sm" dangerouslySetInnerHTML={{ __html: note.note || note.text || note.body || "" }} />
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">
                                            {note.note_type || "General"}
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
};

export default CaseNotes;
