import React, { useEffect, useState, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, Terminal } from 'lucide-react';

const SystemLogs = () => {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const logsEndRef = useRef(null);

    const fetchLogs = async () => {
        try {
            const response = await fetch('/api/logs?limit=500');
            if (response.ok) {
                const data = await response.json();
                setLogs(data.logs);
            }
        } catch (error) {
            console.error("Failed to fetch logs:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
        const interval = setInterval(() => {
            if (autoRefresh) {
                fetchLogs();
            }
        }, 3000);

        return () => clearInterval(interval);
    }, [autoRefresh]);

    useEffect(() => {
        // Auto-scroll to bottom on new logs
        if (logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [logs]);

    return (
        <Card className="h-[calc(100vh-8rem)]">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <div>
                    <CardTitle className="flex items-center gap-2">
                        <Terminal className="h-5 w-5" />
                        System Logs
                    </CardTitle>
                    <CardDescription>Real-time backend activity stream</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setAutoRefresh(!autoRefresh)}
                        className={autoRefresh ? "text-green-500" : "text-muted-foreground"}
                    >
                        {autoRefresh ? "Live" : "Paused"}
                    </Button>
                    <Button variant="outline" size="icon" onClick={fetchLogs}>
                        <RefreshCw className="h-4 w-4" />
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                <div className="h-full max-h-[70vh] w-full rounded-md border bg-black p-4 text-xs text-green-400 font-mono overflow-auto">
                    {loading ? (
                        <div>Loading logs...</div>
                    ) : (
                        logs.length > 0 ? (
                            logs.map((log, index) => (
                                <div key={index} className="whitespace-pre-wrap">{log}</div>
                            ))
                        ) : (
                            <div className="text-muted-foreground">No logs available.</div>
                        )
                    )}
                    <div ref={logsEndRef} />
                </div>
            </CardContent>
        </Card>
    );
};

export default SystemLogs;
