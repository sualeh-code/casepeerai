
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, AlertTriangle, CheckCircle, Search } from 'lucide-react';
import { Button } from "@/components/ui/button";

const DocumentFeed = () => {
    const [documents, setDocuments] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchDocuments = async () => {
        try {
            const response = await fetch('/internal-api/documents?limit=20');
            if (response.ok) {
                const data = await response.json();
                setDocuments(data);
            }
        } catch (error) {
            console.error("Failed to fetch documents:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchDocuments();
        const interval = setInterval(fetchDocuments, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    const lowConfidenceDocs = documents.filter(doc => doc.confidence < 0.85 && !doc.is_reviewed);

    if (loading && documents.length === 0) return <div>Loading document feed...</div>;

    return (
        <Card className="col-span-4 lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                    Smart Document Feed
                </CardTitle>
                <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                    {lowConfidenceDocs.length > 0 && (
                        <div className="bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-md border border-yellow-200 dark:border-yellow-700">
                            <div className="flex items-center gap-2 text-yellow-800 dark:text-yellow-200 font-medium mb-2">
                                <AlertTriangle className="h-4 w-4" />
                                {lowConfidenceDocs.length} Documents Need Review
                            </div>
                            <div className="space-y-2">
                                {lowConfidenceDocs.slice(0, 3).map(doc => (
                                    <div key={doc.id} className="flex items-center justify-between text-sm bg-white dark:bg-slate-800 p-2 rounded shadow-sm">
                                        <span className="truncate max-w-[150px]">{doc.file_name}</span>
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs text-red-500 font-bold">{(doc.confidence * 100).toFixed(0)}%</span>
                                            <Button size="sm" variant="outline" className="h-6 text-xs">Review</Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Recent Processed</h4>
                        {documents.slice(0, 5).map(doc => (
                            <div key={doc.id} className="flex items-center justify-between p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors">
                                <div className="flex items-center gap-3">
                                    <div className={`p-1.5 rounded-full ${doc.confidence >= 0.85 ? 'bg-green-100 text-green-600' : 'bg-yellow-100 text-yellow-600'}`}>
                                        {doc.confidence >= 0.85 ? <CheckCircle className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="text-sm font-medium">{doc.file_name}</span>
                                        <span className="text-xs text-muted-foreground">{doc.category_id}</span>
                                    </div>
                                </div>
                                <span className="text-xs font-mono text-muted-foreground">{(doc.confidence * 100).toFixed(0)}%</span>
                            </div>
                        ))}
                        {documents.length === 0 && (
                            <div className="text-center py-8 text-muted-foreground text-sm">
                                No documents processed yet.
                            </div>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
};

export default DocumentFeed;
