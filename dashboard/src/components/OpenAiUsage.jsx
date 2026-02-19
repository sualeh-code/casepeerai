import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

const OpenAiUsage = () => {
    const [openAiStats, setOpenAiStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/internal-api/integrations/openai/usage');
                if (res.ok) setOpenAiStats(await res.json());
            } catch (err) {
                console.error("Failed to fetch OpenAI usage:", err);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-bold tracking-tight">OpenAI Usage</h2>
            <Card>
                <CardHeader>
                    <CardTitle>OpenAI Live Stats</CardTitle>
                    <CardDescription>Live data fetched from OpenAI (Admin/Org Key required for full stats)</CardDescription>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-muted-foreground">Loading...</div>
                    ) : (
                        <pre className="bg-muted p-4 rounded-md overflow-auto max-h-[500px] text-sm">
                            {openAiStats ? JSON.stringify(openAiStats, null, 2) : "No data available. Check your OpenAI API key in Settings."}
                        </pre>
                    )}
                </CardContent>
            </Card>
        </div>
    );
};

export default OpenAiUsage;
