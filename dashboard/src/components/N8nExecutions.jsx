import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

const N8nExecutions = () => {
    const [n8nStats, setN8nStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/internal-api/integrations/n8n/executions');
                if (res.ok) setN8nStats(await res.json());
            } catch (err) {
                console.error("Failed to fetch n8n executions:", err);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    if (loading) return <div className="p-8 text-muted-foreground">Loading n8n data...</div>;

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-bold tracking-tight">n8n Executions</h2>
            <Card>
                <CardHeader>
                    <CardTitle>Workflow Executions</CardTitle>
                    <CardDescription>Recent execution activity from n8n</CardDescription>
                </CardHeader>
                <CardContent>
                    {n8nStats ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-3 gap-4">
                                <div className="p-4 border rounded-lg bg-green-50">
                                    <div className="text-sm font-medium text-green-800">Success</div>
                                    <div className="text-2xl font-bold text-green-600">{n8nStats.success}</div>
                                </div>
                                <div className="p-4 border rounded-lg bg-red-50">
                                    <div className="text-sm font-medium text-red-800">Errors</div>
                                    <div className="text-2xl font-bold text-red-600">{n8nStats.error}</div>
                                </div>
                                <div className="p-4 border rounded-lg">
                                    <div className="text-sm font-medium text-gray-800">Total Fetched</div>
                                    <div className="text-2xl font-bold">{n8nStats.total_fetched}</div>
                                </div>
                            </div>
                            <div className="border rounded-md">
                                <div className="p-3 bg-muted font-medium">Recent Executions</div>
                                {n8nStats.recent_executions?.length > 0 ? (
                                    n8nStats.recent_executions.map((exec, i) => (
                                        <div key={i} className="p-3 border-t flex justify-between items-center text-sm">
                                            <span className="font-mono">{exec.id}</span>
                                            <span className={exec.finished ? "text-green-600 font-medium" : "text-red-600 font-medium"}>
                                                {exec.finished ? "Success" : "Failed/Running"}
                                            </span>
                                        </div>
                                    ))
                                ) : (
                                    <div className="p-3 border-t text-muted-foreground text-sm">No recent executions</div>
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="text-muted-foreground">No data. Check n8n API key and URL in Settings.</div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
};

export default N8nExecutions;
